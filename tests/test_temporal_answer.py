"""As-of answering on the /query path (Phase 8 / track 1, Task 2).

Pins the real FADCS ladder as the oracle, the inclusive boundary rule, the
supersession text, every fail-closed branch (pre-range, unmatched, missing
artifact), the strictly-additive no-``as_of`` invariant, and the anti-
fabrication guarantee that the cited span literally appears in its source.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest

import app.temporal_answer as temporal_answer_mod
from app.schemas import QueryRequest, QueryResponse
from app.temporal_answer import (
    match_scheme,
    temporal_answer,
)

ROOT = Path(__file__).resolve().parent.parent
FADCS = ROOT / "data" / "myscheme" / "fadcs.md"

REFUSAL_MARKER = "current or latest value has been substituted"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- resolution and boundary --------------------------------------------------


def test_as_of_inside_a_range_returns_the_governing_value():
    payload = temporal_answer(
        "What was the FADCS child allowance rate?", date(2021, 1, 1)
    )
    assert payload["mode"] == "as_of"
    assert "₹1,350" in payload["answer"]
    assert "2020-01-01" in payload["answer"]
    assert "₹1,600" in payload["answer"]
    assert "2021-04-01" in payload["answer"]
    assert payload["sources"][0]["source"] == "data/myscheme/fadcs.md"


def test_boundary_is_inclusive_on_the_effective_date():
    old = temporal_answer("FADCS rate", date(2021, 3, 31))
    new = temporal_answer("FADCS rate", date(2021, 4, 1))
    assert "₹1,350" in old["answer"]
    assert "₹1,600" in new["answer"]


def test_supersession_text_names_the_replacement_and_its_date():
    payload = temporal_answer("FADCS rate", date(2021, 1, 1))
    assert "₹1,600" in payload["answer"]
    assert "2021-04-01" in payload["answer"]
    assert "took over" in payload["answer"]


def test_last_claim_reports_no_later_value_rather_than_refusing():
    payload = temporal_answer("FADCS rate", date(2024, 1, 1))
    assert "₹1,850" in payload["answer"]
    assert "most recent declared value" in payload["answer"]


def test_iso_string_and_date_agree():
    assert temporal_answer("FADCS rate", "2021-01-01")["answer"] == (
        temporal_answer("FADCS rate", date(2021, 1, 1))["answer"]
    )


# --- fail-closed branches (R4) ------------------------------------------------


def test_date_before_the_first_effective_date_refuses_and_names_the_earliest():
    payload = temporal_answer("FADCS rate", date(2000, 1, 1))
    assert payload["mode"] == "as_of"
    assert payload["sources"] == []
    assert "No declared value is recorded" in payload["answer"]
    assert "2009-03-01" in payload["answer"]
    assert "₹200" in payload["answer"]
    assert REFUSAL_MARKER in payload["answer"].lower()
    # It must not present the current/latest value as the answer.
    assert "₹1,850" not in payload["answer"]


def test_unmatched_scheme_refuses_without_guessing():
    payload = temporal_answer("What is the weather in Paris?", date(2021, 1, 1))
    assert payload["mode"] == "as_of"
    assert payload["sources"] == []
    assert "could not be matched" in payload["answer"]
    assert REFUSAL_MARKER in payload["answer"].lower()


def test_ambiguous_scheme_match_fails_closed():
    claims = temporal_answer_mod.load_claims()
    assert claims is not None
    # "children" is a distinctive token of both the FADCS and the
    # non-school-going disabled children ladders, so the match is ambiguous.
    assert match_scheme("children", claims) is None


def test_missing_artifact_degrades_gracefully(monkeypatch, tmp_path):
    missing = tmp_path / "no_such_claims.jsonl"
    monkeypatch.setattr(
        temporal_answer_mod, "claims_fixture_path", lambda: missing
    )
    payload = temporal_answer("FADCS rate", date(2021, 1, 1))
    assert payload["mode"] == "as_of"
    assert payload["sources"] == []
    assert "unavailable" in payload["answer"]
    assert REFUSAL_MARKER in payload["answer"].lower()


# --- anti-fabrication ---------------------------------------------------------


def test_cited_span_literally_appears_in_its_named_source():
    payload = temporal_answer("FADCS rate", date(2021, 1, 1))
    span = payload["sources"][0]["content"]
    assert "₹1350/- w.e.f. 01.01.2020" == span
    source_text = _normalise(FADCS.read_text(encoding="utf-8"))
    assert _normalise(span) in source_text


# --- request-schema validation (R1) -------------------------------------------


def test_malformed_as_of_is_rejected_not_ignored():
    for bad in ("2021-1-1", "01-01-2021", "not-a-date", "2021-13-01", "2021-02-30"):
        with pytest.raises(Exception):
            QueryRequest(question="valid question", as_of=bad)


def test_valid_as_of_parses_and_absence_stays_none():
    assert QueryRequest(question="valid question", as_of="2021-01-01").as_of == (
        date(2021, 1, 1)
    )
    assert QueryRequest(question="valid question").as_of is None


# --- the response shape is unchanged without as_of (R3) -----------------------


def test_query_response_schema_did_not_gain_an_as_of_field():
    assert set(QueryResponse.model_fields) == {
        "answer",
        "sources",
        "quotes",
        "steps",
        "mode",
        "notice",
        "language",
    }


@pytest.fixture
def demo_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "groq_api_key", "")
    return TestClient(app)


def test_no_as_of_payload_is_the_pre_change_shape(demo_client):
    resp = demo_client.post("/query", json={"question": "What is PM-KISAN?"})
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload) == {
        "answer",
        "sources",
        "quotes",
        "steps",
        "mode",
        "notice",
        "language",
    }
    assert "as_of" not in payload
    assert payload["mode"] == "demo"


def test_as_of_request_returns_as_of_mode(demo_client):
    resp = demo_client.post(
        "/query",
        json={
            "question": "What was the FADCS child allowance rate?",
            "as_of": "2021-01-01",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "as_of"
    assert "₹1,350" in payload["answer"]
    assert payload["sources"][0]["source"] == "data/myscheme/fadcs.md"


def test_malformed_as_of_is_422_on_the_endpoint(demo_client):
    resp = demo_client.post(
        "/query", json={"question": "valid question", "as_of": "2021-1-1"}
    )
    assert resp.status_code == 422


# --- the SSE path supports as_of (R1) -----------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _parse_sse(text: str):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


@pytest.mark.anyio
async def test_stream_supports_as_of(monkeypatch):
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "groq_api_key", "")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/query/stream",
            json={
                "question": "What was the FADCS child allowance rate?",
                "as_of": "2021-01-01",
            },
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0][0] == "sources"
    assert events[-1][0] == "done"
    assert events[-1][1]["mode"] == "as_of"
    answer_text = "".join(d["text"] for e, d in events if e == "token")
    assert "₹1,350" in answer_text


# --- app/ does not import eval/ (R5) ------------------------------------------


def test_temporal_answer_module_reads_data_without_importing_eval():
    code = (
        "import app.temporal_answer\n"
        "import sys\n"
        "assert 'eval' not in sys.modules, 'app must not import eval/'\n"
        "assert 'app.db' not in sys.modules\n"
        "assert 'app.rag' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
