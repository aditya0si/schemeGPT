"""Operator control plane for a deployed SchemeGPT instance.

This is the *field-facing* half of the product: the controls an engineer needs
after go-live, when the customer's environment, the network, or the model
provider misbehaves. Three controls, all in-process and thread-safe:

1. **AI kill switch** — stop LLM generation for this instance and serve
   retrieval-only answers instead, so the service stays up and honest while a
   human decides what to do. The switch survives a restart (persisted to a
   small JSON file), because a kill switch that a redeploy silently undoes is
   not a kill switch.
2. **Provider circuit breaker** — after N consecutive provider failures the
   breaker opens for a cooldown; requests are not sent to a provider that is
   already failing (no request pile-up, no cascading timeouts), then exactly
   one half-open probe decides whether to close again.
3. **Provider endpoint override** — repoint the LLM client at the customer's
   API gateway / egress proxy (or a secondary provider) at runtime, without a
   rebuild or a redeploy. This is the knob that makes "route our traffic
   through your corporate proxy" a five-minute change instead of a release.

Design rules this module holds to:

* **Never raise from a control path.** A control plane that crashes the data
  plane is worse than no control plane; every mutator is defensive.
* **No secrets, no provider error text.** Snapshots expose states, counts and
  a masked endpoint only, so ``/ops/status`` is safe to expose. Provider
  exception *types* are kept (``RateLimitError``), their messages are not.
* **Transient vs durable state is a decision, not an accident.** The kill
  switch is durable; breaker state is deliberately in-memory, because a
  process restart is a fresh chance for the provider.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from app import metrics

logger = logging.getLogger(__name__)

# Circuit breaker states.
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

# Counter names (all surfaced by GET /metrics).
COUNTER_AI_DISABLED = "ai_disabled_total"
COUNTER_DEGRADED_ANSWERS = "degraded_answers_total"
COUNTER_BREAKER_REJECTED = "breaker_rejected_total"
COUNTER_BREAKER_TRIPS = "breaker_trips_total"
COUNTER_PROVIDER_FAILURES = "provider_failures_total"
COUNTER_PROVIDER_SUCCESSES = "provider_successes_total"
COUNTER_KILL_SWITCH_CHANGES = "kill_switch_changes_total"

# Bounded audit trail of operator actions. Bounded on purpose: an unbounded
# in-process audit log is a memory leak on a long-lived instance.
AUDIT_MAX_ENTRIES = 50

_ACTOR_MAX = 64
_REASON_MAX = 200
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _clean(text: str | None, limit: int) -> str:
    """Collapse whitespace, drop control characters and truncate.

    Operator-supplied strings are stored and echoed back in status output;
    this keeps a pasted stack trace or an embedded newline from corrupting
    the audit trail or the status payload. Failure text from a provider is
    *never* passed through here — only exception type names are kept.
    """
    if not text:
        return ""
    collapsed = " ".join(_CONTROL_CHARS.sub(" ", str(text)).split())
    return collapsed[:limit]


def mask_url(url: str | None) -> str | None:
    """Return a log-safe form of a URL: scheme + host + path, nothing else.

    Userinfo and query strings are dropped: a corporate gateway URL or a
    secondary-provider endpoint can carry an embedded credential or API key,
    and status output is not the place for either.
    """
    if not url or not str(url).strip():
        return None
    try:
        parts = urlsplit(str(url).strip())
    except ValueError:
        return "<unparsable>"
    if not parts.scheme or not parts.netloc:
        return "<unparsable>"
    host = parts.netloc.rsplit("@", 1)[-1]  # strip any user:pass@ prefix
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{host}{path}"


def validate_base_url(url: str) -> str:
    """Validate an operator-supplied provider base URL.

    Returns the normalized URL (trailing slash removed). Raises ``ValueError``
    with a message that never echoes the input, so a URL carrying a key cannot
    leak into an HTTP error response.
    """
    candidate = str(url or "").strip()
    if not candidate:
        raise ValueError("base URL must not be empty")
    if any(ch.isspace() for ch in candidate):
        raise ValueError("base URL must not contain whitespace")
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https"):
        raise ValueError("base URL must start with http:// or https://")
    if not parts.netloc:
        raise ValueError("base URL must include a host")
    return candidate.rstrip("/")


class ProviderBreaker:
    """Consecutive-failure circuit breaker around the LLM provider.

    States: ``closed`` (normal) -> ``open`` (rejecting) -> ``half_open`` (one
    probe) -> back to ``closed`` on success or ``open`` on failure.

    The clock is injectable so the cooldown can be tested without sleeping.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout_s: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock or time.monotonic
        self.failure_threshold = max(1, int(failure_threshold))
        self.reset_timeout_s = max(0.0, float(reset_timeout_s))
        self.half_open_max_calls = max(1, int(half_open_max_calls))
        self._state = CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0
        self._trips = 0
        self._rejected = 0
        self._last_error_type: str | None = None

    # -- decision ---------------------------------------------------------
    def allow(self) -> bool:
        """True when a provider call may be attempted right now."""
        with self._lock:
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                opened_at = self._opened_at or self._clock()
                if (self._clock() - opened_at) >= self.reset_timeout_s:
                    self._state = HALF_OPEN
                    self._half_open_in_flight = 1
                    logger.info("Provider breaker half-open: sending one probe.")
                    return True
                self._rejected += 1
                return False
            # half_open
            if self._half_open_in_flight < self.half_open_max_calls:
                self._half_open_in_flight += 1
                return True
            self._rejected += 1
            return False

    # -- outcome ----------------------------------------------------------
    def record_success(self) -> None:
        with self._lock:
            if self._state != CLOSED:
                logger.info(
                    "Provider breaker closed after a successful call (trips=%d).",
                    self._trips,
                )
            self._state = CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_flight = 0

    def record_failure(self, error_type: str = "Unknown") -> bool:
        """Record a provider failure. Returns True if the circuit just opened."""
        with self._lock:
            self._half_open_in_flight = 0
            self._last_error_type = _clean(error_type, 64) or "Unknown"
            self._consecutive_failures += 1
            if self._state == HALF_OPEN:
                # A failed probe re-opens immediately: the provider is still
                # unhealthy, and one probe is enough evidence.
                self._open_locked()
                return True
            if self._consecutive_failures >= self.failure_threshold:
                self._open_locked()
                return True
            return False

    def _open_locked(self) -> None:
        self._state = OPEN
        self._opened_at = self._clock()
        self._trips += 1
        logger.warning(
            "Provider breaker OPEN after %d consecutive failures (last=%s); "
            "retrieval-only answers for %.0fs.",
            self._consecutive_failures,
            self._last_error_type,
            self.reset_timeout_s,
        )

    def reset(self) -> None:
        with self._lock:
            self._state = CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_flight = 0

    # -- introspection ----------------------------------------------------
    @property
    def state(self) -> str:
        with self._lock:
            # Report a state that is true *now*: an open breaker past its
            # cooldown is half-open in effect even before the first probe.
            if (
                self._state == OPEN
                and self._opened_at is not None
                and (self._clock() - self._opened_at) >= self.reset_timeout_s
            ):
                return HALF_OPEN
            return self._state

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            opened_at = self._opened_at
            state = self._state
            payload = {
                "state": state,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "half_open_in_flight": self._half_open_in_flight,
                "trips": self._trips,
                "rejected": self._rejected,
                "reset_timeout_s": self.reset_timeout_s,
                "last_error_type": self._last_error_type,
            }
        if state == OPEN and opened_at is not None:
            seconds = max(0.0, self._clock() - opened_at)
            payload["open_for_s"] = round(seconds, 2)
            payload["closes_in_s"] = round(
                max(0.0, self.reset_timeout_s - seconds), 2
            )
        else:
            payload["open_for_s"] = None
            payload["closes_in_s"] = None
        # Report the effective view (past cooldown reads as half_open).
        payload["state"] = self.state
        return payload


class OpsController:
    """Process-wide operator state: kill switch, breaker, provider endpoint.

    One instance is created at import time (``ops``) from application settings.
    Tests construct their own instance with a temporary state file.
    """

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        breaker: ProviderBreaker | None = None,
        ai_enabled: bool = True,
        configured_base_url: str = "",
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock or time.time
        self.breaker = breaker or ProviderBreaker(clock=clock)
        self._state_path = state_path
        self._configured_base_url = (configured_base_url or "").strip()
        self._base_url_override: str | None = None
        self._ai_enabled = bool(ai_enabled)
        self._disabled_since: str | None = None
        self._disabled_reason: str = ""
        self._audit: deque[dict[str, Any]] = deque(maxlen=AUDIT_MAX_ENTRIES)
        persisted = self._load()
        if persisted is not None:
            self._ai_enabled = bool(persisted.get("ai_enabled", self._ai_enabled))
            if not self._ai_enabled:
                self._disabled_since = persisted.get("updated_at") or self._now()
                self._disabled_reason = _clean(
                    persisted.get("reason"), _REASON_MAX
                )
            logger.warning(
                "Operator state restored from %s: ai_enabled=%s",
                self._state_path,
                self._ai_enabled,
            )

    # -- helpers ----------------------------------------------------------
    def _now(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).isoformat(
            timespec="seconds"
        )

    def _record(self, action: str, actor: str, reason: str = "") -> None:
        entry = {
            "at": self._now(),
            "action": action,
            "actor": _clean(actor, _ACTOR_MAX) or "unspecified",
            "reason": _clean(reason, _REASON_MAX),
        }
        with self._lock:
            self._audit.append(entry)

    # -- persistence ------------------------------------------------------
    def _load(self) -> dict[str, Any] | None:
        if self._state_path is None:
            return None
        try:
            if not self._state_path.exists():
                return None
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("operator state file is not a JSON object")
            return data
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Ignoring unreadable operator state file %s (%s); using "
                "configured defaults.",
                self._state_path,
                type(exc).__name__,
            )
            return None

    def _persist(self) -> None:
        """Atomically write the durable part of the operator state.

        Write-temp-then-replace: a crash mid-write must never leave a
        half-written state file that a restart would read as "enabled".
        Failures are logged, never raised — the in-memory switch still holds
        for the life of the process.
        """
        if self._state_path is None:
            return
        payload = {
            "schema": 1,
            "ai_enabled": self._ai_enabled,
            "reason": self._disabled_reason,
            "updated_at": self._disabled_since or self._now(),
        }
        tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self._state_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Could not persist operator state to %s (%s); the kill switch "
                "remains active for this process only.",
                self._state_path,
                type(exc).__name__,
            )

    # -- kill switch ------------------------------------------------------
    @property
    def ai_enabled(self) -> bool:
        return self._ai_enabled

    def disable_ai(self, reason: str = "", actor: str = "") -> dict[str, Any]:
        """Turn AI generation off for this instance and persist the decision."""
        self._ai_enabled = False
        self._disabled_since = self._now()
        self._disabled_reason = _clean(reason, _REASON_MAX)
        self._record("ai_disabled", actor, reason)
        metrics.inc(COUNTER_KILL_SWITCH_CHANGES)
        metrics.inc(COUNTER_AI_DISABLED)
        self._persist()
        logger.warning(
            "AI generation DISABLED by '%s' (reason=%r). /query serves "
            "retrieval-only answers until it is re-enabled.",
            _clean(actor, _ACTOR_MAX) or "unspecified",
            self._disabled_reason,
        )
        return self.status(include_audit=True)

    def enable_ai(self, actor: str = "", reason: str = "") -> dict[str, Any]:
        """Turn AI generation back on."""
        self._ai_enabled = True
        self._disabled_since = None
        self._disabled_reason = ""
        self._record("ai_enabled", actor, reason)
        metrics.inc(COUNTER_KILL_SWITCH_CHANGES)
        self._persist()
        logger.warning(
            "AI generation ENABLED by '%s'.",
            _clean(actor, _ACTOR_MAX) or "unspecified",
        )
        return self.status(include_audit=True)

    # -- provider endpoint ------------------------------------------------
    def set_provider_base_url(
        self, base_url: str, actor: str = "", reason: str = ""
    ) -> dict[str, Any]:
        """Point the LLM client at another endpoint (gateway, proxy, mirror).

        Passing an empty string clears the override and returns to the
        configured value (``GROQ_API_BASE``). Raises ``ValueError`` for an
        invalid URL; the error message never echoes the input.
        """
        if not str(base_url or "").strip():
            self._base_url_override = None
            self._record("provider_endpoint_cleared", actor, reason)
            logger.warning("Provider endpoint override cleared (back to configured).")
            return self.status(include_audit=True)
        validated = validate_base_url(base_url)
        self._base_url_override = validated
        self._record("provider_endpoint_set", actor, f"{mask_url(validated)} {reason}")
        logger.warning(
            "Provider endpoint override set to %s (in-memory only; set "
            "GROQ_API_BASE to make it durable).",
            mask_url(validated),
        )
        return self.status(include_audit=True)

    def provider_base_url(self) -> str:
        """Effective provider base URL ('' means the client default)."""
        effective = self._base_url_override or self._configured_base_url
        try:
            return validate_base_url(effective) if effective else ""
        except ValueError:  # pragma: no cover - config typo
            logger.warning(
                "Configured GROQ_API_BASE value is not a valid base URL; ignoring it."
            )
            return ""

    # -- introspection ----------------------------------------------------
    def status(self, *, include_audit: bool = False) -> dict[str, Any]:
        """Operator snapshot: safe to expose (no reasons, no URLs with keys)."""
        effective = self.provider_base_url()
        with self._lock:
            audit_count = len(self._audit)
            audit = list(self._audit)
        counters = metrics.snapshot().get("counters", {})
        payload: dict[str, Any] = {
            "version": self._build_version(),
            "ai": {
                "enabled": self._ai_enabled,
                "state": "enabled" if self._ai_enabled else "disabled",
                "disabled_since": self._disabled_since,
                "kill_switch_changes": counters.get(COUNTER_KILL_SWITCH_CHANGES, 0),
            },
            "breaker": self.breaker.snapshot(),
            "provider": {
                "endpoint": mask_url(effective),
                "override_active": self._base_url_override is not None,
                "configured_endpoint_present": bool(self._configured_base_url),
            },
            "degraded_answers": {
                "total": counters.get(COUNTER_DEGRADED_ANSWERS, 0),
                "ai_disabled_skips": counters.get(COUNTER_AI_DISABLED, 0),
                "breaker_rejections": counters.get(COUNTER_BREAKER_REJECTED, 0),
                "breaker_trips": counters.get(COUNTER_BREAKER_TRIPS, 0),
                "provider_failures": counters.get(COUNTER_PROVIDER_FAILURES, 0),
                "provider_successes": counters.get(COUNTER_PROVIDER_SUCCESSES, 0),
            },
            "audit_entries": audit_count,
        }
        if include_audit:
            payload["audit"] = audit
        return payload

    def audit(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._audit)

    def _build_version(self) -> str:
        """Build identity of the running code (``GIT_SHA`` injected at build)."""
        try:
            from app.config import settings

            return settings.git_sha.strip() or "dev"
        except Exception:  # pragma: no cover - defensive
            return "dev"

    # -- call-path helpers ------------------------------------------------
    def gate(self) -> str:
        """Why provider calls are (dis)allowed right now: for callers/telemetry.

        Returns ``"kill_switch"``, ``"breaker"`` or ``"ok"``. Increments the
        matching counter so both refusals are visible in /metrics without the
        caller having to remember which one happened.
        """
        if not self._ai_enabled:
            metrics.inc(COUNTER_AI_DISABLED)
            return "kill_switch"
        if not self.breaker.allow():
            metrics.inc(COUNTER_BREAKER_REJECTED)
            return "breaker"
        return "ok"

    def record_provider_success(self) -> None:
        metrics.inc(COUNTER_PROVIDER_SUCCESSES)
        self.breaker.record_success()

    def record_provider_failure(self, error_type: str) -> bool:
        """Record a provider failure; True if this failure opened the circuit."""
        metrics.inc(COUNTER_PROVIDER_FAILURES)
        opened = self.breaker.record_failure(error_type)
        if opened:
            metrics.inc(COUNTER_BREAKER_TRIPS)
        return opened

    def reset(self) -> None:
        """Test/dev helper: back to the configured defaults."""
        self._ai_enabled = True
        self._disabled_since = None
        self._disabled_reason = ""
        self._base_url_override = None
        self.breaker.reset()
        with self._lock:
            self._audit.clear()


def build_ops_controller() -> OpsController:
    """Construct the process-wide controller from settings (import side-effect)."""
    from app.config import ROOT_DIR, settings

    state_file = Path(settings.ops_state_file)
    if not state_file.is_absolute():
        state_file = ROOT_DIR / state_file
    return OpsController(
        state_path=state_file,
        breaker=ProviderBreaker(
            failure_threshold=settings.breaker_failure_threshold,
            reset_timeout_s=settings.breaker_reset_timeout_s,
        ),
        ai_enabled=settings.ops_ai_enabled,
        configured_base_url=settings.groq_api_base,
    )


ops = build_ops_controller()
