"""Operator control plane: kill switch, circuit breaker, degraded answers.

No database, no network, no LLM: the breaker uses an injected clock, retriever
calls are stubbed with fake documents, and the operator controller is built
against a temporary state file so a developer's real ``var/ops_state.json`` is
never touched by a test run.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ops as ops_module
from app.ops import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    OpsController,
    ProviderBreaker,
    mask_url,
    validate_base_url,
)


class FakeClock:
    """Monotonic-ish clock a test can advance by hand."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def breaker(clock):
    return ProviderBreaker(
        failure_threshold=2, reset_timeout_s=30.0, clock=clock
    )


@pytest.fixture
def controller(tmp_path, clock):
    return OpsController(
        state_path=tmp_path / "ops_state.json",
        breaker=ProviderBreaker(failure_threshold=2, reset_timeout_s=30.0, clock=clock),
        clock=clock,
    )


# --- circuit breaker ---------------------------------------------------------


def test_breaker_closed_allows_calls(breaker):
    assert breaker.state == CLOSED
    assert breaker.allow() is True
    breaker.record_failure("RateLimitError")
    assert breaker.state == CLOSED  # below threshold
    assert breaker.allow() is True


def test_breaker_opens_at_threshold_and_rejects(breaker):
    breaker.record_failure("RateLimitError")
    opened = breaker.record_failure("RateLimitError")
    assert opened is True
    assert breaker.state == OPEN
    assert breaker.allow() is False
    snapshot = breaker.snapshot()
    assert snapshot["trips"] == 1
    assert snapshot["rejected"] == 1
    assert snapshot["last_error_type"] == "RateLimitError"
    assert snapshot["closes_in_s"] == 30.0


def test_breaker_half_open_probe_after_cooldown(breaker, clock):
    breaker.record_failure("Timeout")
    breaker.record_failure("Timeout")
    clock.advance(29.0)
    assert breaker.allow() is False  # still inside the cooldown
    clock.advance(1.5)
    # Cooldown elapsed: report half-open and allow exactly one probe.
    assert breaker.state == HALF_OPEN
    assert breaker.allow() is True
    assert breaker.allow() is False  # single-flight probe
    assert breaker.snapshot()["state"] == HALF_OPEN


def test_failed_probe_reopens_and_successful_probe_closes(breaker, clock):
    breaker.record_failure("HTTPStatusError")
    breaker.record_failure("HTTPStatusError")
    clock.advance(31.0)
    assert breaker.allow() is True
    breaker.record_failure("HTTPStatusError")
    assert breaker.state == OPEN
    assert breaker.snapshot()["trips"] == 2

    clock.advance(31.0)
    assert breaker.allow() is True
    breaker.record_success()
    assert breaker.state == CLOSED
    assert breaker.snapshot()["consecutive_failures"] == 0
    assert breaker.snapshot()["open_for_s"] is None


def test_breaker_reset_clears_state(breaker):
    breaker.record_failure("boom")
    breaker.record_failure("boom")
    breaker.reset()
    assert breaker.state == CLOSED
    assert breaker.allow() is True


# --- URL handling ------------------------------------------------------------


def test_mask_url_strips_credentials_and_query():
    masked = mask_url("https://user:secret@llm-gw.customer.internal/groq/v1?key=abc123")
    assert masked == "https://llm-gw.customer.internal/groq/v1"
    assert "secret" not in masked
    assert "abc123" not in masked


def test_mask_url_handles_empty_and_garbage():
    assert mask_url("") is None
    assert mask_url(None) is None
    assert mask_url("not-a-url") == "<unparsable>"


def test_validate_base_url_accepts_and_normalizes():
    assert validate_base_url("https://gw.example/v1/") == "https://gw.example/v1"
    assert validate_base_url(" http://127.0.0.1:9099/v1 ") == "http://127.0.0.1:9099/v1"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "ftp://gw.example", "gw.example/v1", "https://gw example/v1"],
)
def test_validate_base_url_rejects_bad_values(value):
    with pytest.raises(ValueError):
        validate_base_url(value)


# --- kill switch -------------------------------------------------------------


def test_kill_switch_survives_restart(tmp_path, clock):
    state_file = tmp_path / "ops_state.json"
    first = OpsController(state_path=state_file, clock=clock)
    assert first.ai_enabled is True
    first.disable_ai(reason="provider billing dispute", actor="oncall-aditya")
    assert first.ai_enabled is False

    # A new process (new controller over the same file) must come up disabled.
    second = OpsController(state_path=state_file, clock=clock)
    assert second.ai_enabled is False
    assert second.status()["ai"]["state"] == "disabled"

    second.enable_ai(actor="oncall-aditya")
    third = OpsController(state_path=state_file, clock=clock)
    assert third.ai_enabled is True


def test_kill_switch_state_file_is_valid_json(tmp_path, clock):
    state_file = tmp_path / "nested" / "ops_state.json"
    controller = OpsController(state_path=state_file, clock=clock)
    controller.disable_ai(reason="data quality review", actor="field-eng")
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["ai_enabled"] is False
    assert payload["schema"] == 1
    assert payload["reason"] == "data quality review"
    # No temp file left behind by the atomic write.
    assert not list(state_file.parent.glob("*.tmp"))


def test_unreadable_state_file_falls_back_to_defaults(tmp_path, clock):
    state_file = tmp_path / "ops_state.json"
    state_file.write_text("{not json", encoding="utf-8")
    controller = OpsController(state_path=state_file, clock=clock)
    assert controller.ai_enabled is True


def test_audit_trail_is_sanitized_bounded_and_private(tmp_path, clock):
    controller = OpsController(state_path=tmp_path / "ops.json", clock=clock)
    controller.disable_ai(reason="line1\nline2\twith\x00controls", actor="a" * 200)
    entry = controller.audit()[-1]
    assert "\n" not in entry["reason"] and "\t" not in entry["reason"]
    assert len(entry["actor"]) == ops_module._ACTOR_MAX
    # Public status must not leak the reason text.
    assert "line1" not in json.dumps(controller.status())

    for index in range(ops_module.AUDIT_MAX_ENTRIES + 10):
        controller.enable_ai(actor=f"op{index}")
    assert len(controller.audit()) == ops_module.AUDIT_MAX_ENTRIES
    controller.enable_ai(actor="last")
    assert controller.audit()[-1]["actor"] == "last"


# --- provider endpoint -------------------------------------------------------


def test_provider_endpoint_override_and_clear(tmp_path, clock):
    controller = OpsController(
        state_path=tmp_path / "ops.json",
        configured_base_url="https://default.example/v1",
        clock=clock,
    )
    assert controller.provider_base_url() == "https://default.example/v1"
    assert controller.status()["provider"]["override_active"] is False

    controller.set_provider_base_url("https://gw.customer.internal/groq/v1")
    assert controller.provider_base_url() == "https://gw.customer.internal/groq/v1"
    status = controller.status()
    assert status["provider"]["override_active"] is True
    assert status["provider"]["endpoint"] == "https://gw.customer.internal/groq/v1"

    controller.set_provider_base_url("")
    assert controller.provider_base_url() == "https://default.example/v1"
    assert controller.status()["provider"]["override_active"] is False


def test_invalid_configured_base_url_is_ignored(tmp_path, clock):
    controller = OpsController(
        state_path=tmp_path / "ops.json",
        configured_base_url="llm-gw.internal/v1",
        clock=clock,
    )
    assert controller.provider_base_url() == ""
    assert controller.status()["provider"]["configured_endpoint_present"] is True


# --- gate accounting ---------------------------------------------------------


def test_gate_reports_reason_and_counts(tmp_path, clock):
    from app import metrics

    controller = OpsController(
        state_path=tmp_path / "ops.json",
        breaker=ProviderBreaker(failure_threshold=1, clock=clock),
        clock=clock,
    )
    assert controller.gate() == "ok"

    controller.breaker.record_failure("Timeout")
    assert controller.gate() == "breaker"

    controller.breaker.reset()
    controller.disable_ai(reason="drill")
    assert controller.gate() == "kill_switch"

    counters = metrics.snapshot()["counters"]
    assert counters.get("breaker_rejected_total", 0) >= 1
    assert counters.get("ai_disabled_total", 0) >= 1


def test_record_provider_failure_counts_trips(tmp_path, clock, monkeypatch):
    from app import metrics

    controller = OpsController(
        state_path=tmp_path / "ops.json",
        breaker=ProviderBreaker(failure_threshold=1, clock=clock),
        clock=clock,
    )
    assert controller.record_provider_failure("RateLimitError") is True
    controller.record_provider_failure("RateLimitError")
    counters = metrics.snapshot()["counters"]
    assert counters["provider_failures_total"] >= 2
    assert counters["breaker_trips_total"] >= 1
    controller.record_provider_success()
    assert controller.breaker.state == CLOSED


# --- degraded (retrieval-only) answers ---------------------------------------


class FakeDoc:
    def __init__(self, source, content, status="sample_verified"):
        self.page_content = content
        self.metadata = {
            "source": source,
            "jurisdiction": "central",
            "state": None,
            "data_status": status,
            "last_verified": "2026-01-01",
            "source_url": "https://example.gov.in/x",
        }


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, _query):
        return list(self.docs)


PM_KISAN = (
    "PM-KISAN provides income support of Rs 6,000 per year to eligible "
    "landholding farmer families. The amount is paid in three equal "
    "instalments of Rs 2,000 every four months. Landholding farmers must "
    "complete eKYC to receive the instalment."
)


@pytest.fixture
def degraded_setup(monkeypatch, tmp_path):
    """Wire a fake retriever + a controller whose AI switch is off."""
    from app import rag

    controller = OpsController(state_path=tmp_path / "ops.json")
    monkeypatch.setattr(rag, "operator", controller)
    monkeypatch.setattr(rag, "get_retriever", lambda: FakeRetriever(
        [FakeDoc("schemes/pm-kisan.md", PM_KISAN)]
    ))
    monkeypatch.setattr(
        rag, "get_llm", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("degraded mode must never call the LLM")
        )
    )
    controller.disable_ai(reason="test", actor="pytest")
    return rag, controller


def test_degraded_answer_quotes_are_verbatim_and_verified(degraded_setup):
    from app.quotes import parse_quotes, verify_quotes

    rag, _controller = degraded_setup
    payload = rag.degraded_answer(
        "How much money does PM-KISAN pay a farmer?", "en"
    )
    assert payload["mode"] == "degraded"
    assert payload["notice"] and "AI generation is disabled" in payload["notice"]
    assert payload["sources"][0]["source"] == "schemes/pm-kisan.md"

    quotes = parse_quotes(payload["answer"])
    assert quotes, "degraded answers must cite source lines"
    verified = verify_quotes(quotes, payload["sources"])
    assert all(q.verified for q in verified)
    # Every cited line really is a substring of the source document.
    for quote in quotes:
        assert quote.text in PM_KISAN


def test_degraded_answer_is_localized(degraded_setup):
    rag, _controller = degraded_setup
    payload = rag.degraded_answer("पीएम-किसान से कितना पैसा मिलता है?", "hi")
    assert payload["language"] == "hi"
    assert payload["notice"] == rag.DEGRADED_NOTICE_HI


def test_answer_short_circuits_when_kill_switch_is_off(degraded_setup, monkeypatch):
    rag, controller = degraded_setup
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")
    payload = rag.answer("How much does PM-KISAN pay?")
    assert payload["mode"] == "degraded"
    assert "PM-KISAN" in payload["answer"]
    assert controller.breaker.snapshot()["state"] == CLOSED


def test_fallback_answer_uses_demo_when_retrieval_fails(monkeypatch, tmp_path):
    from app import rag

    controller = OpsController(state_path=tmp_path / "ops.json")

    class ExplodingRetriever:
        def invoke(self, _query):
            raise RuntimeError("database is down")

    monkeypatch.setattr(rag, "get_retriever", lambda: ExplodingRetriever())
    payload = rag.fallback_answer("anything", "en", None, reason="provider_failure")
    assert payload["mode"] == "demo"
    assert payload["notice"]
    # The controller is only here to prove the demo path needs no operator state.
    assert controller.ai_enabled is True


# --- provider call bounds -----------------------------------------------------
# Measured in the no-egress rehearsal: with the SDK's own defaults (no timeout,
# two retries with backoff) a provider that accepts the connection and then goes
# silent left requests hanging for ~150s before the retrieval-only fallback ran.
# The client is bounded now, and this test keeps it that way.


def test_llm_client_bounds_the_provider_call(monkeypatch):
    from app import rag
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")
    llm = rag.get_llm()

    assert llm.request_timeout == settings.groq_timeout_s
    assert llm.max_retries == settings.groq_max_retries
    # A citizen-facing answer must degrade in bounded time; anything above a
    # minute is indistinguishable from an outage to the person waiting.
    assert settings.groq_timeout_s <= 60
    assert settings.groq_max_retries <= 1


# --- operator state vs the semantic cache -------------------------------------
# The two refusal reasons deliberately differ. A human stopping generation must
# stop *serving* generated text, so a cached live answer is not replayed; a
# failing provider is an availability problem, so a cached answer is still the
# best answer available. Both are asserted here because the difference is a
# product decision, not an implementation detail.


def test_kill_switch_bypasses_the_semantic_cache(degraded_setup, monkeypatch):
    rag, _controller = degraded_setup
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")
    cached_live = {
        "answer": "generated text that a human may distrust",
        "sources": [],
        "mode": "live",
        "language": "en",
    }
    lookups = {"count": 0}

    def counting_lookup(*_args, **_kwargs):
        lookups["count"] += 1
        return cached_live

    monkeypatch.setattr(rag.semantic_cache, "lookup", counting_lookup)
    payload = rag.answer("How much does PM-KISAN pay a farmer family?")

    assert payload["mode"] == "degraded"
    assert lookups["count"] == 0, "the cache must not even be consulted while generation is stopped"


def test_breaker_still_serves_cached_answers(degraded_setup, monkeypatch):
    rag, controller = degraded_setup
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")
    controller.enable_ai(actor="pytest")  # undo the fixture's kill switch
    for _ in range(controller.breaker.failure_threshold):
        controller.breaker.record_failure("Timeout")
    assert controller.breaker.state == OPEN

    cached_live = {
        "answer": "previously generated and verified answer",
        "sources": [],
        "mode": "live",
        "language": "en",
    }
    monkeypatch.setattr(rag.semantic_cache, "lookup", lambda *_a, **_k: cached_live)
    payload = rag.answer("How much does PM-KISAN pay a farmer family?")

    assert payload["mode"] == "live"
    assert payload.get("cached") is True


def test_breaker_without_cache_serves_retrieval_only(degraded_setup, monkeypatch):
    rag, controller = degraded_setup
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")
    controller.enable_ai(actor="pytest")
    for _ in range(controller.breaker.failure_threshold):
        controller.breaker.record_failure("Timeout")
    monkeypatch.setattr(rag.semantic_cache, "lookup", lambda *_a, **_k: None)
    payload = rag.answer("How much does PM-KISAN pay a farmer family?")

    assert payload["mode"] == "degraded"


# --- HTTP surface ------------------------------------------------------------


@pytest.fixture
def ops_client(monkeypatch, tmp_path):
    """TestClient over the operator endpoints, with no database involved.

    The app is deliberately *not* entered as a context manager: the FastAPI
    lifespan ingests the corpus and probes the database, neither of which these
    tests need. ``/health``'s DB probe is stubbed with a no-op connection so
    the liveness contract can still be asserted without a running Postgres.
    """
    from app import main as main_module
    from app import rag, stream
    from app.config import settings

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute(self, *_args, **_kwargs):
            return None

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    controller = OpsController(state_path=tmp_path / "ops.json")
    monkeypatch.setattr(main_module, "operator", controller)
    monkeypatch.setattr(main_module, "get_engine", lambda: _FakeEngine())
    monkeypatch.setattr(rag, "operator", controller)
    monkeypatch.setattr(stream, "operator", controller)
    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    client = TestClient(main_module.app)
    try:
        yield client, controller
    finally:
        client.close()


def test_status_endpoint_is_public_and_leaks_nothing(ops_client):
    client, controller = ops_client
    controller.disable_ai(reason="customer escalation ticket INC-42", actor="oncall")
    response = client.get("/ops/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ai"]["state"] == "disabled"
    assert body["breaker"]["state"] == "closed"
    assert set(body) == {
        "version",
        "ai",
        "breaker",
        "provider",
        "degraded_answers",
        "audit_entries",
    }
    assert "INC-42" not in response.text


def test_control_endpoints_require_admin_token(ops_client, monkeypatch):
    client, _controller = ops_client
    from app.config import settings

    assert client.post("/ops/ai", json={"enabled": False}).status_code == 401
    assert client.post(
        "/ops/ai", json={"enabled": False}, headers={"X-Admin-Token": "wrong"}
    ).status_code == 401
    assert client.get("/ops/audit").status_code == 401

    # Without a configured token the endpoint is disabled, not open.
    monkeypatch.setattr(settings, "admin_token", "")
    response = client.post(
        "/ops/ai", json={"enabled": False}, headers={"X-Admin-Token": "anything"}
    )
    assert response.status_code == 503


def test_kill_switch_endpoint_round_trip(ops_client):
    client, controller = ops_client
    headers = {"X-Admin-Token": "test-admin-token"}

    off = client.post(
        "/ops/ai",
        json={"enabled": False, "reason": "provider outage", "actor": "oncall"},
        headers=headers,
    )
    assert off.status_code == 200
    assert off.json()["ai"]["state"] == "disabled"
    assert controller.ai_enabled is False

    audit = client.get("/ops/audit", headers=headers).json()["audit"]
    assert audit[-1]["action"] == "ai_disabled"
    assert audit[-1]["actor"] == "oncall"

    on = client.post("/ops/ai", json={"enabled": True}, headers=headers)
    assert on.status_code == 200
    assert on.json()["ai"]["state"] == "enabled"


def test_provider_endpoint_validation_and_override(ops_client):
    client, controller = ops_client
    headers = {"X-Admin-Token": "test-admin-token"}

    bad = client.post(
        "/ops/provider", json={"base_url": "gw.internal/v1"}, headers=headers
    )
    assert bad.status_code == 400
    assert "gw.internal" not in bad.json()["detail"]  # never echo the input

    ok = client.post(
        "/ops/provider",
        json={"base_url": "http://127.0.0.1:9099/v1", "actor": "field-eng"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["provider"]["override_active"] is True
    assert controller.provider_base_url() == "http://127.0.0.1:9099/v1"


def test_health_reports_operator_state_without_flapping(ops_client):
    client, controller = ops_client
    healthy = client.get("/health").json()
    assert healthy["status"] == "ok"
    assert healthy["ai"] == "enabled"

    controller.disable_ai(reason="drill")
    disabled = client.get("/health").json()
    # The service is still up: a human pressed a switch, nothing is down.
    assert disabled["status"] == "ok"
    assert disabled["ai"] == "disabled"
    assert disabled["provider_circuit"] == "closed"
