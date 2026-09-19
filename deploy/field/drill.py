#!/usr/bin/env python3
"""Rehearse the things that go wrong in front of a customer — on purpose.

This drives a *real* running deployment through a scripted sequence and records
what happened, so the numbers in the runbook are measured rather than asserted:

    A. install the previous release        (baseline, no operator control plane)
    B. upgrade to this release             (snapshot, gate, smoke, row count)
    C. ship a deliberately broken release  (must fail the gate, must auto-roll back)
    D. operator kill switch                (degrade, survive a restart, restore)
    E. provider outage                     (breaker opens, degraded answers, recovery)
    F. no egress at all                    (retrieval-only still answers, quotes verified)
    G. host preflight in air-gap mode      (recorded findings for the engagement)

Every phase writes into one JSON report plus a Markdown summary under
``docs/evidence/``. Nothing here talks to a real LLM provider: a local stub
(``stub_provider.py``) is pointed at through the operator endpoint, so the drill
is deterministic, free, and safe to run in front of anyone.

Usage:
    python3 deploy/field/drill.py --phases A,B,C,D,E,F,G
    python3 deploy/field/drill.py --phases E --skip-install
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import socket
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent
REPO_ROOT = FIELD_DIR.parents[1]
REPORTS_DIR = FIELD_DIR / "reports"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence"
API = os.environ.get("SCHEMEGPT_API_URL", "http://127.0.0.1:8000")
STUB_PORT = int(os.environ.get("SCHEMEGPT_STUB_PORT", "9099"))
STUB_BASE_URL = f"http://host.docker.internal:{STUB_PORT}/openai/v1"

BASELINE_VERSION = "v1.0.0"
RELEASE_VERSION = "v2.0.0"
BROKEN_VERSION = "v2.0.1"

DRY_RUN = False
LOG_LINES: list[str] = []


def log(message: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, flush=True)
    LOG_LINES.append(line)


def run(argv: list[str], check: bool = True, timeout: int = 1800) -> subprocess.CompletedProcess:
    log(f"$ {' '.join(argv)}")
    if DRY_RUN:
        return subprocess.CompletedProcess(argv, 0, "", "")
    result = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    tail = (result.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        LOG_LINES.append(f"    | {line}")
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n"
            f"{(result.stderr or '')[-2000:]}"
        )
    return result


def sh_script(script: Path) -> str:
    """Repo-relative POSIX path for handing a shell script to bash.

    An absolute Windows path is mangled by the MSYS runtime (backslashes are
    eaten, and the interpreter ends up looking for a file called
    ``C:Users...``), so shell scripts are always addressed relative to the
    repository root with forward slashes.
    """
    return script.relative_to(REPO_ROOT).as_posix()


# --- HTTP helpers ------------------------------------------------------------


def http(method: str, path: str, payload: dict | None = None, timeout: float = 30.0,
         headers: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def ops_status() -> dict:
    status, body = http("GET", "/ops/status")
    return body if status == 200 else {}


def admin_headers() -> dict:
    return {"X-Admin-Token": os.environ.get("SCHEMEGPT_ADMIN_TOKEN", "")}


def unique_question(base: str = "How much income support does PM-KISAN provide") -> str:
    """Every drill call asks something new: the semantic cache would otherwise
    answer the second identical question from the first one, hiding the outage."""
    nonce = "".join(random.choices(string.ascii_lowercase, k=6))
    return f"{base} ({nonce})?"


def ask(mode: str = "en") -> dict:
    started = time.perf_counter()
    status, body = http(
        "POST",
        "/query",
        {"question": unique_question(), "language": mode},
        timeout=120,
    )
    return {
        "status": status,
        "mode": body.get("mode"),
        "sources": len(body.get("sources") or []),
        "answer_chars": len(body.get("answer") or ""),
        "elapsed_s": round(time.perf_counter() - started, 2),
        "body": body,
    }


def stream_once() -> dict:
    """Drive /query/stream and summarise the SSE events we care about."""
    payload = json.dumps({"question": unique_question("What is the PM-KISAN instalment")}).encode()
    request = urllib.request.Request(
        f"{API}/query/stream", data=payload, headers={"Content-Type": "application/json"}
    )
    events: list[tuple[str, dict]] = []
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            event_name = None
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: ") and event_name:
                    try:
                        events.append((event_name, json.loads(line[6:])))
                    except json.JSONDecodeError:
                        events.append((event_name, {}))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "events": []}
    done = next((data for name, data in events if name == "done"), {})
    return {
        "events": [name for name, _ in events],
        "done": done,
        "tokens": sum(1 for name, _ in events if name == "token"),
        "sources": len(next((data for name, data in events if name == "sources"), []) or []),
        "elapsed_s": round(time.perf_counter() - started, 2),
    }


def wait_healthy(timeout: int = 900) -> float:
    started = time.time()
    while time.time() - started < timeout:
        status, body = http("GET", "/health", timeout=10)
        if status == 200 and body.get("status") == "ok":
            return round(time.time() - started, 2)
        time.sleep(5)
    raise RuntimeError(f"stack did not become healthy within {timeout}s")


def verify_quotes_from_answer(answer: str, sources: list[dict]) -> dict:
    """Independent check that every cited line really exists in its source.

    Deliberately re-implemented here rather than imported from the app: the
    drill should not be able to pass by agreeing with the code it is testing.
    """
    cited = []
    for line in answer.splitlines():
        match = re.match(r"^\s*>\s*(?P<text>.+?)\s*\[(?P<source>[^\],]+)(?:,\s*(?P<status>[a-z_]+))?\]\s*$", line)
        if match:
            cited.append((match.group("text"), match.group("source")))
    contents = {" ".join(str(s.get("content", "")).lower().split()): s.get("source", "") for s in sources}
    checked = []
    for text, source in cited:
        needle = " ".join(text.lower().split())
        found_in = [name for blob, name in contents.items() if needle in blob]
        checked.append(
            {
                "source": source,
                "verified": bool(found_in),
                "matched": found_in[0] if found_in else None,
            }
        )
    return {
        "cited": len(cited),
        "verified": sum(1 for item in checked if item["verified"]),
        "details": checked,
    }


# --- stub provider -----------------------------------------------------------


class Stub:
    """The local stand-in provider, started in-process for the drill."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(FIELD_DIR / "stub_provider.py"), "--port", str(STUB_PORT)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", STUB_PORT), timeout=1):
                    log(f"stub provider up on port {STUB_PORT}")
                    return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("stub provider did not start")

    def mode(self, value: str) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{STUB_PORT}/control",
            data=json.dumps({"mode": value}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())

    def stats(self) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{STUB_PORT}/stats", timeout=10) as response:
            return json.loads(response.read().decode())

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


# --- phase helpers -----------------------------------------------------------


def env_file() -> Path:
    return REPO_ROOT / ".env"


def read_env() -> dict:
    values: dict[str, str] = {}
    for line in env_file().read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def set_env(key: str, value: str) -> None:
    """Set a key in .env, preserving everything else."""
    path = env_file()
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith(f"{key}=")
    ]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_admin_token() -> str:
    values = read_env()
    token = values.get("ADMIN_TOKEN", "").strip()
    if not token:
        token = "drill-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=24))
        set_env("ADMIN_TOKEN", token)
        log("Generated an ADMIN_TOKEN for the drill (written to .env, never printed)")
    os.environ["SCHEMEGPT_ADMIN_TOKEN"] = token
    return token


def pinned_image() -> str:
    """Read the image pin written by lib.sh into state/deploy.env."""
    path = FIELD_DIR / "state" / "deploy.env"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("SCHEMEGPT_API_IMAGE="):
            return line.split("=", 1)[1].strip()
    return ""


def set_pinned_image(reference: str) -> None:
    """Pin the API image for compose, in the kit's own env file (never .env)."""
    state_dir = FIELD_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "deploy.env"
    lines = []
    if path.exists():
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("SCHEMEGPT_API_IMAGE=")
        ]
    lines.append(f"SCHEMEGPT_API_IMAGE={reference}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deployed_state(version: str, image: str, previous: str = "", previous_image: str = "") -> None:
    """Mirror what install.sh/upgrade.sh record, so the drill is reproducible."""
    state_dir = FIELD_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": version,
        "image": image,
        "previous_version": previous,
        "previous_image": previous_image,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (state_dir / "deployed.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def image_exists(reference: str) -> bool:
    if DRY_RUN:
        return True
    result = subprocess.run(
        ["docker", "image", "inspect", reference],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    argv = [
        "docker",
        "compose",
        "-f",
        str(REPO_ROOT / "docker-compose.yml"),
        "--env-file",
        str(REPO_ROOT / ".env"),
    ]
    deploy_env = FIELD_DIR / "state" / "deploy.env"
    if deploy_env.exists():
        argv += ["--env-file", str(deploy_env)]
    return run([*argv, *args], check=check)


# --- phases ------------------------------------------------------------------


def phase_install_baseline(report: dict) -> None:
    """A: the release the customer is running today, installed from its image."""
    log("PHASE A: install the baseline release")
    if not image_exists(f"schemegpt:{BASELINE_VERSION}"):
        raise RuntimeError(
            f"schemegpt:{BASELINE_VERSION} not found. Build it first:\n"
            "  git stash && docker build -t schemegpt:v1.0.0 . && git stash pop"
        )
    set_pinned_image(f"schemegpt:{BASELINE_VERSION}")
    compose("up", "-d", "--no-build", "db", "api")
    health_seconds = wait_healthy(timeout=1500)
    status, ops = http("GET", "/ops/status")
    smoke = ask()
    # Record what is deployed, exactly as install.sh does. Without this the
    # next upgrade has no "from" version and its rollback target is guesswork.
    write_deployed_state(f"schemegpt:{BASELINE_VERSION}", f"schemegpt:{BASELINE_VERSION}")
    report["A_install_baseline"] = {
        "image": f"schemegpt:{BASELINE_VERSION}",
        "health_seconds": health_seconds,
        "ops_status_code": status,
        "operator_endpoints": "present" if status == 200 else "absent (baseline build)",
        "first_answer_mode": smoke["mode"],
        "first_answer_sources": smoke["sources"],
        "answer_seconds": smoke["elapsed_s"],
    }
    log(f"PHASE A done: healthy in {health_seconds}s, /ops/status -> {status}")


def phase_upgrade(report: dict) -> None:
    """B: the real upgrade path, with snapshot + gate + smoke + row count."""
    log(f"PHASE B: upgrade {BASELINE_VERSION} -> {RELEASE_VERSION}")
    if not image_exists(f"schemegpt-api:{RELEASE_VERSION}"):
        raise RuntimeError(f"schemegpt-api:{RELEASE_VERSION} is missing; build it first.")
    if report.get("A_install_baseline"):
        # The state file is written by install.sh in a real engagement; when the
        # drill starts from a baseline installed by compose alone, seed it.
        pass
    started = time.time()
    result = run(
        [
            "bash",
            sh_script(FIELD_DIR / "upgrade.sh"),
            "--to-version",
            RELEASE_VERSION,
            "--wait",
            "600",
        ],
        check=False,
    )
    status = ops_status()
    smoke = ask()
    report["B_upgrade"] = {
        "exit_code": result.returncode,
        "seconds": round(time.time() - started, 2),
        "reported_version": status.get("version"),
        "ai_state": (status.get("ai") or {}).get("state"),
        "post_upgrade_mode": smoke["mode"],
        "batch_log": (result.stdout or "").strip().splitlines()[-12:],
    }
    if result.returncode != 0:
        raise RuntimeError(f"upgrade failed:\n{result.stderr[-2000:]}")
    log(
        f"PHASE B done in {report['B_upgrade']['seconds']}s; "
        f"version reported by the API: {status.get('version')}"
    )


def phase_broken_release(report: dict) -> None:
    """C: a release that must fail — and must clean up after itself."""
    log(f"PHASE C: ship a broken release ({BROKEN_VERSION}) and require a rollback")
    healthy_before = {"mode": ask()["mode"], "status": ops_status()}

    # Build the bad release: same image, one broken setting. This is the most
    # common real failure — not a bad binary, a bad configuration value shipped
    # with it — and it is exactly what an automated rollback has to survive.
    set_env("EMBEDDING_MODEL", "intfloat/this-model-does-not-exist-on-purpose")
    log("Injected EMBEDDING_MODEL=intfloat/this-model-does-not-exist-on-purpose")

    started = time.time()
    result = run(
        [
            "bash",
            sh_script(FIELD_DIR / "upgrade.sh"),
            "--to-version",
            BROKEN_VERSION,
            "--to-image",
            f"schemegpt-api:{RELEASE_VERSION}",
            "--wait",
            "120",
        ],
        check=False,
    )
    after = ops_status()
    healthy_after = ask()
    report["C_broken_release"] = {
        "exit_code": result.returncode,
        "seconds": round(time.time() - started, 2),
        "expected_exit_code": 1,
        "rolled_back_to_version": after.get("version"),
        "healthy_after_rollback": healthy_after["mode"],
        "mode_before": healthy_before["mode"],
        "log_tail": (result.stdout or "").strip().splitlines()[-14:],
        "detect_to_recover_seconds": None,
    }
    # Timings parsed from the deploy records written by upgrade.sh/rollback.sh.
    records = sorted((FIELD_DIR / "logs").glob("*.json"))
    if records:
        report["C_broken_release"]["records"] = [path.name for path in records[-4:]]
    if result.returncode != 1:
        raise RuntimeError(
            f"broken release did not fail the way it must (exit {result.returncode}); "
            "the gate is not protecting the deployment."
        )
    if healthy_after["mode"] == "000":
        raise RuntimeError("after the rollback the API is not answering")
    log(
        f"PHASE C done: broken release rejected, rolled back to "
        f"{after.get('version')}, API answering in mode {healthy_after['mode']}"
    )


def phase_kill_switch(report: dict) -> None:
    """D: an operator stops AI generation — and it stays stopped."""
    log("PHASE D: operator kill switch")
    headers = admin_headers()
    before = ask()

    status, body = http(
        "POST",
        "/ops/ai",
        {
            "enabled": False,
            "reason": "drill: stale corpus pending re-verification",
            "actor": "drill.py",
        },
        headers=headers,
    )
    if status != 200:
        raise RuntimeError(f"kill switch call failed: {status} {body}")

    degraded = ask()
    quote_check = verify_quotes_from_answer(
        degraded["body"].get("answer", ""), degraded["body"].get("sources") or []
    )
    streamed = stream_once()

    log("Restarting the API container to prove the switch survives a restart")
    compose("restart", "api")
    health_seconds = wait_healthy(timeout=600)
    after_restart = ops_status()
    post_restart_answer = ask()

    http("POST", "/ops/ai", {"enabled": True, "actor": "drill.py"}, headers=headers)
    restored = ask()

    report["D_kill_switch"] = {
        "mode_before": before["mode"],
        "mode_disabled": degraded["mode"],
        "degraded_answer_sources": degraded["sources"],
        "degraded_answer_seconds": degraded["elapsed_s"],
        "quotes": quote_check,
        "stream_events": streamed.get("events"),
        "stream_done_mode": (streamed.get("done") or {}).get("mode"),
        "restart_health_seconds": health_seconds,
        "ai_state_after_restart": (after_restart.get("ai") or {}).get("state"),
        "mode_after_restart": post_restart_answer["mode"],
        "mode_after_reenable": restored["mode"],
        "audit_entries": after_restart.get("audit_entries"),
    }
    if degraded["mode"] != "degraded":
        raise RuntimeError(f"kill switch did not degrade answers (got {degraded['mode']})")
    if quote_check["cited"] and quote_check["verified"] != quote_check["cited"]:
        raise RuntimeError(f"degraded answers contain unverifiable citations: {quote_check}")
    if (after_restart.get("ai") or {}).get("state") != "disabled":
        raise RuntimeError("the kill switch did not survive the container restart")
    log(
        f"PHASE D done: degraded answers are citation-verified "
        f"({quote_check['verified']}/{quote_check['cited']}), switch survived restart"
    )


def phase_provider_outage(report: dict, stub: Stub) -> None:
    """E: the provider starts failing; the system must notice and recover."""
    log("PHASE E: provider outage rehearsal")
    headers = admin_headers()

    # Point generation at the local stub through the operator endpoint — the
    # same control an engineer uses to route through a customer gateway.
    status, body = http(
        "POST",
        "/ops/provider",
        {"base_url": STUB_BASE_URL, "actor": "drill.py", "reason": "outage rehearsal"},
        headers=headers,
    )
    if status != 200:
        raise RuntimeError(f"provider override failed: {status} {body}")

    stub.mode("ok")
    baseline_modes = [ask()["mode"] for _ in range(3)]
    log(f"stub healthy: answer modes {baseline_modes}")
    if "live" not in baseline_modes:
        raise RuntimeError(
            "the stub is not being used for generation; the override or the base URL "
            f"is wrong (modes: {baseline_modes})"
        )

    before = ops_status()
    breakers_before = (before.get("breaker") or {}).get("trips", 0)

    log("Stub provider -> rate_limit (429 + Retry-After)")
    stub.mode("rate_limit")
    ouch_started = time.perf_counter()
    attempts: list[dict] = []
    opened_at = None
    for index in range(8):
        result = ask()
        attempts.append({"mode": result["mode"], "status": result["status"], "s": result["elapsed_s"]})
        snapshot = ops_status()
        if (
            opened_at is None
            and (snapshot.get("breaker") or {}).get("state") == "open"
        ):
            opened_at = round(time.perf_counter() - ouch_started, 2)
            log(f"circuit opened after {opened_at}s of failing calls ({index + 1} attempts)")
        time.sleep(0.4)
    during = ops_status()
    streamed = stream_once()
    stats_during = stub.stats()

    # Heal the provider and measure how long the deployment takes to trust it
    # again: the cooldown must elapse, then one probe must succeed.
    log("Stub provider -> ok (recovery measurement)")
    stub.mode("ok")
    recovery_started = time.perf_counter()
    recovered_after = None
    modes_after_heal: list[str] = []
    while time.perf_counter() - recovery_started < 180:
        mode = ask()["mode"]
        modes_after_heal.append(mode)
        if mode == "live":
            recovered_after = round(time.perf_counter() - recovery_started, 2)
            break
        time.sleep(2)

    http("POST", "/ops/provider", {"base_url": "", "actor": "drill.py"}, headers=headers)
    after = ops_status()

    report["E_provider_outage"] = {
        "stub_base_url": STUB_BASE_URL,
        "healthy_answer_modes": baseline_modes,
        "time_to_circuit_open_s": opened_at,
        "attempts_during_outage": attempts,
        "degraded_answers_served": sum(1 for a in attempts if a["mode"] == "degraded"),
        "stream_during_outage": {
            "events": streamed.get("events"),
            "done_mode": (streamed.get("done") or {}).get("mode"),
            "sources": streamed.get("sources"),
        },
        "breaker_before": (before.get("breaker") or {}),
        "breaker_after": (after.get("breaker") or {}),
        "trips_delta": (after.get("breaker") or {}).get("trips", 0) - breakers_before,
        "provider_failures": (after.get("degraded_answers") or {}).get("provider_failures"),
        "breaker_rejections": (after.get("degraded_answers") or {}).get("breaker_rejections"),
        "stub_requests_by_mode": stats_during.get("counts"),
        "recovery_seconds": recovered_after,
        "modes_after_heal": modes_after_heal,
    }
    if opened_at is None:
        raise RuntimeError("the circuit never opened during a sustained provider outage")
    if recovered_after is None:
        raise RuntimeError("the deployment never returned to live answers after the provider healed")
    log(
        f"PHASE E done: circuit opened in {opened_at}s, "
        f"{report['E_provider_outage']['degraded_answers_served']} degraded answers served, "
        f"recovered in {recovered_after}s"
    )


def phase_no_egress(report: dict, stub: Stub) -> None:
    """F: no route to any provider at all — retrieval-only must still answer."""
    log("PHASE F: no-egress behaviour (air-gap runtime)")
    headers = admin_headers()
    stub.mode("unreachable")
    http(
        "POST",
        "/ops/provider",
        {"base_url": STUB_BASE_URL, "actor": "drill.py", "reason": "no-egress rehearsal"},
        headers=headers,
    )
    results = [ask() for _ in range(4)]
    worst = results[-1]
    quotes = verify_quotes_from_answer(
        worst["body"].get("answer", ""), worst["body"].get("sources") or []
    )
    streamed = stream_once()
    http("POST", "/ops/provider", {"base_url": "", "actor": "drill.py"}, headers=headers)
    # Recover the stack for whoever uses it next.
    stub.mode("ok")
    time.sleep(1)
    final = ask()
    report["F_no_egress"] = {
        "answer_modes": [r["mode"] for r in results],
        "sources_returned": worst["sources"],
        "answer_seconds": worst["elapsed_s"],
        "quotes": quotes,
        "stream_done_mode": (streamed.get("done") or {}).get("mode"),
        "recovered_mode": final["mode"],
    }
    if any(r["mode"] == "000" for r in results):
        raise RuntimeError("the API stopped answering when the provider was unreachable")
    log(
        f"PHASE F done: modes {report['F_no_egress']['answer_modes']}, "
        f"citations verified {quotes['verified']}/{quotes['cited']}"
    )


def phase_preflight(report: dict) -> None:
    """G: the host report an engineer attaches to the engagement."""
    log("PHASE G: air-gap preflight record")
    path = REPORTS_DIR / f"preflight-airgap-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    result = run(
        [
            sys.executable,
            str(FIELD_DIR / "preflight.py"),
            "--repo-root",
            str(REPO_ROOT),
            "--airgap",
            "--label",
            "drill-airgap",
            "--json",
            str(path),
        ],
        check=False,
    )
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report["G_preflight_airgap"] = {
        "exit_code": result.returncode,
        "verdict": payload.get("verdict"),
        "counts": payload.get("counts"),
        "blockers": [f["code"] for f in payload.get("findings", []) if f["severity"] == "BLOCKER"],
        "report": str(path.relative_to(REPO_ROOT)),
    }
    log(f"PHASE G done: verdict {payload.get('verdict')} ({payload.get('counts')})")


# --- reporting ---------------------------------------------------------------


def write_evidence(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    json_path = REPORTS_DIR / f"drill-{stamp}.json"
    report["meta"] = {
        "tool": "schemegpt-field-drill",
        "at": stamp,
        "host": socket.gethostname(),
        "api": API,
        "baseline_version": BASELINE_VERSION,
        "release_version": RELEASE_VERSION,
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    md_path = EVIDENCE_DIR / "FIELD-DRILL.md"
    sections: list[str] = []
    a = report.get("A_install_baseline")
    if a:
        sections.append(
            "## A — Install the previous release\n\n"
            f"- image `{a['image']}`, healthy in **{a['health_seconds']}s**\n"
            f"- `/ops/status` → `{a['ops_status_code']}` ({a['operator_endpoints']})\n"
            f"- first answer: mode `{a['first_answer_mode']}`, "
            f"{a['first_answer_sources']} sources, {a['answer_seconds']}s\n"
        )
    b = report.get("B_upgrade")
    if b:
        sections.append(
            "## B — Upgrade to this release\n\n"
            f"- exit `{b['exit_code']}` in **{b['seconds']}s**\n"
            f"- API reports version `{b['reported_version']}`, AI `{b['ai_state']}`\n"
            f"- post-upgrade answer mode `{b['post_upgrade_mode']}`\n"
        )
    c = report.get("C_broken_release")
    if c:
        sections.append(
            "## C — Deliberately broken release\n\n"
            f"- shipped with a bad `EMBEDDING_MODEL`; upgrade exited **{c['exit_code']}** "
            f"(expected `{c['expected_exit_code']}`) after {c['seconds']}s\n"
            f"- automatic rollback left the API on version `{c['rolled_back_to_version']}`, "
            f"answering `{c['healthy_after_rollback']}`\n"
        )
    d = report.get("D_kill_switch")
    if d:
        sections.append(
            "## D — Operator kill switch\n\n"
            f"- live → `{d['mode_disabled']}` on demand, {d['degraded_answer_seconds']}s per answer, "
            f"{d['degraded_answer_sources']} sources\n"
            f"- citations verified: **{d['quotes']['verified']}/{d['quotes']['cited']}**\n"
            f"- SSE stream `done.mode = {d['stream_done_mode']}`\n"
            f"- container restarted (healthy in {d['restart_health_seconds']}s): "
            f"AI state still `{d['ai_state_after_restart']}`, answers still `{d['mode_after_restart']}`\n"
            f"- re-enabled → `{d['mode_after_reenable']}`\n"
        )
    e = report.get("E_provider_outage")
    if e:
        sections.append(
            "## E — Provider outage\n\n"
            f"- healthy baseline modes `{e['healthy_answer_modes']}` (against the local stub)\n"
            f"- **circuit opened {e['time_to_circuit_open_s']}s** into sustained 429s\n"
            f"- degraded answers served during the outage: "
            f"{e['degraded_answers_served']} of {len(e['attempts_during_outage'])} attempts\n"
            f"- SSE stream during the outage: `done.mode = "
            f"{(e['stream_during_outage'] or {}).get('done_mode')}`\n"
            f"- provider calls rejected by the breaker while open: {e['breaker_rejections']}\n"
            f"- **recovery after the provider healed: {e['recovery_seconds']}s** "
            f"(cooldown + one successful probe)\n"
        )
    f_block = report.get("F_no_egress")
    if f_block:
        sections.append(
            "## F — No egress at all\n\n"
            f"- answer modes while unreachable: `{f_block['answer_modes']}`\n"
            f"- retrieval still returned {f_block['sources_returned']} sources; "
            f"citations verified {f_block['quotes']['verified']}/{f_block['quotes']['cited']}\n"
            f"- SSE `done.mode = {f_block['stream_done_mode']}`; "
            f"after the provider returned: `{f_block['recovered_mode']}`\n"
        )
    g = report.get("G_preflight_airgap")
    if g:
        sections.append(
            "## G — Air-gap preflight\n\n"
            f"- verdict `{g['verdict']}`, counts `{g['counts']}`, blockers {g['blockers'] or 'none'}\n"
            f"- record: `{g['report']}`\n"
        )

    md_path.write_text(
        "# Field drill — measured results\n\n"
        "Generated by `deploy/field/drill.py` against a real Docker Compose deployment.\n"
        "Every number below is a measurement from that run, not a target. Raw JSON "
        f"report: `deploy/field/reports/{json_path.name}`.\n\n"
        + "\n".join(sections)
        + "\n## How to reproduce\n\n"
        "```bash\n"
        "# baseline image (the release the drill starts from)\n"
        "git stash && docker build -t schemegpt:v1.0.0 . && git stash pop\n"
        "docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t schemegpt-api:v2.0.0 .\n"
        "python3 deploy/field/drill.py --phases A,B,C,D,E,F,G\n"
        "```\n",
        encoding="utf-8",
    )
    return md_path


def main() -> int:
    global DRY_RUN
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phases",
        default="A,B,C,D,E,F,G",
        help="Comma-separated phases to run (default: all).",
    )
    parser.add_argument("--skip-install", action="store_true", help="Alias for --phases without A.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, run nothing.")
    args = parser.parse_args()

    phases = [p.strip().upper() for p in args.phases.split(",") if p.strip()]
    if args.skip_install and "A" in phases:
        phases.remove("A")

    if args.dry_run:
        DRY_RUN = True
        plan = ", ".join(phases)
        print("Dry run: no phase will execute, nothing will be written.")
        print(f"Phases requested: {plan}")
        for phase, description in (
            ("A", f"install the baseline release ({BASELINE_VERSION})"),
            ("B", f"upgrade to {RELEASE_VERSION} (snapshot, health gate, smoke)"),
            ("C", f"ship a broken release ({BROKEN_VERSION}) and require the auto-rollback"),
            ("D", "operator kill switch: degrade, survive a restart, restore"),
            ("E", "provider outage: breaker opens, degraded answers, recovery"),
            ("F", "no egress at all: retrieval-only answers, citations verified"),
            ("G", "air-gap host preflight record"),
        ):
            marker = "->" if phase in phases else "  "
            print(f"  {marker} {phase}: {description}")
        return 0

    if not DRY_RUN:
        if not env_file().exists():
            print(f"FATAL: {env_file()} not found; install the stack first.", file=sys.stderr)
            return 2
        ensure_admin_token()

    report: dict = {}
    stub = Stub()
    started = time.time()
    needs_stub = any(p in phases for p in ("E", "F"))
    try:
        if needs_stub and not DRY_RUN:
            stub.start()
        for phase in phases:
            if phase == "A":
                phase_install_baseline(report)
            elif phase == "B":
                phase_upgrade(report)
            elif phase == "C":
                phase_broken_release(report)
            elif phase == "D":
                phase_kill_switch(report)
            elif phase == "E":
                phase_provider_outage(report, stub)
            elif phase == "F":
                phase_no_egress(report, stub)
            elif phase == "G":
                phase_preflight(report)
            else:
                raise SystemExit(f"unknown phase: {phase}")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nDRILL FAILED: {exc}", file=sys.stderr)
        write_evidence(report)
        return 1
    finally:
        if needs_stub:
            stub.stop()
        # Leave the deployment in the state a customer should find it in.
        if not DRY_RUN:
            headers = admin_headers()
            http("POST", "/ops/ai", {"enabled": True, "actor": "drill.py"}, headers=headers)
            http("POST", "/ops/provider", {"base_url": "", "actor": "drill.py"}, headers=headers)

    report["duration_s"] = round(time.time() - started, 2)
    md_path = write_evidence(report)
    print(f"\nDrill complete in {report['duration_s']}s. Evidence: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
