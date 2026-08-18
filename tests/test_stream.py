"""/query/stream SSE contract in demo mode (no key, no DB, no lifespan).

httpx 0.28's ASGITransport is async-only, so the tests drive the app through
``httpx.AsyncClient``; anyio's pytest plugin (anyio already ships with
FastAPI) runs them without adding any dependency.
"""
import json

import httpx
import pytest

from app.main import app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def parse_sse(text: str):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event, data))
    return events


@pytest.fixture
async def client(monkeypatch):
    # Force demo mode regardless of the developer's local .env key.
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    transport = httpx.ASGITransport(app=app)  # does NOT run lifespan
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client


async def test_stream_demo_event_order_and_content(client):
    resp = await client.post(
        "/query/stream",
        json={"question": "How much income support does PM-KISAN provide?"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    names = [e for e, _ in events]
    assert names[0] == "sources"
    assert "token" in names
    assert names[-1] == "done"

    answer_text = "".join(
        d["text"] for e, d in events if e == "token"
    )
    assert "PM-KISAN" in answer_text
    done = events[-1][1]
    assert done["mode"] == "demo"
    assert done["notice"]
    assert done["language"] == "en"

    sources = events[0][1]
    assert isinstance(sources, list)
    if sources:
        for s in sources:
            assert set(s) >= {
                "source", "content", "jurisdiction", "state",
                "data_status", "last_verified", "source_url",
            }


async def test_stream_hindi_demo(client):
    resp = await client.post(
        "/query/stream",
        json={"question": "पीएम-किसान के तहत कितनी आय सहायता मिलती है?", "language": "hi"},
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["language"] == "hi"


async def test_stream_rejects_short_question(client):
    resp = await client.post("/query/stream", json={"question": "x"})
    assert resp.status_code == 422


async def test_stream_demo_emits_quotes_before_done(client):
    resp = await client.post(
        "/query/stream",
        json={"question": "How much income support does PM-KISAN provide?"},
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    names = [e for e, _ in events]
    assert "quotes" in names
    assert names[-1] == "done"  # the quotes event must precede done
    quotes = next(d for e, d in events if e == "quotes")
    assert quotes, "expected at least one quote"
    q = quotes[0]
    assert set(q) >= {"text", "source", "status", "verified", "matched_source"}
    # The demo answer quotes a real sentence from pm-kisan.md, so it verifies.
    assert q["verified"] is True
    assert q["matched_source"] == "pm-kisan.md"
