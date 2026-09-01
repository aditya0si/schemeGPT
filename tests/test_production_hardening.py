"""Unit tests for Tier 2 production hardening: semantic cache behavior,
token-bucket rate limiting, token-usage accounting, and metrics snapshot."""

import pytest

from app import metrics, ratelimit, semantic_cache
from app.rag import TokenUsageHandler
from app.ratelimit import _TokenBucketStore


@pytest.fixture(autouse=True)
def _reset_metrics():
    with metrics._lock:
        metrics._counters.clear()
        metrics._token_usage.clear()
        metrics._latencies.clear()
    yield


# --- semantic cache -------------------------------------------------------


def test_profile_hash_is_order_insensitive_and_distinct():
    a = semantic_cache.profile_hash({"name": "A", "age": 30})
    b = semantic_cache.profile_hash({"age": 30, "name": "A"})
    assert a == b
    assert a != semantic_cache.profile_hash({"name": "B", "age": 30})
    assert semantic_cache.profile_hash(None) == "none"


def test_lookup_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(
        type(semantic_cache.settings), "enable_semantic_cache", False, raising=False
    )
    assert semantic_cache.lookup("q", "en", "none") is None


def test_lookup_swallows_engine_errors(monkeypatch):
    class Boom:
        def begin(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(semantic_cache, "get_engine", lambda: Boom())
    result = semantic_cache.lookup("q", "en", "none")
    assert result is None
    with metrics._lock:
        assert metrics._counters.get("cache_error", 0) >= 1


def test_store_swallows_engine_errors(monkeypatch):
    class Boom:
        def begin(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(semantic_cache, "get_engine", lambda: Boom())
    semantic_cache.store("q", "en", "none", {"answer": "x"})
    with metrics._lock:
        assert metrics._counters.get("cache_error", 0) >= 1


def test_metrics_snapshot_reports_cache_fields():
    metrics.inc("cache_hit", 3)
    metrics.inc("cache_miss", 1)
    snap = metrics.snapshot()
    assert snap["cache"]["hits"] == 3
    assert snap["cache"]["misses"] == 1
    assert snap["cache"]["hit_rate"] == 0.75


# --- token bucket ---------------------------------------------------------


def test_bucket_allows_burst_then_limits():
    bucket = _TokenBucketStore(capacity=3, refill_per_minute=60)
    allowed, _ = bucket.take("1.2.3.4", now=100.0)
    assert allowed
    assert bucket.take("1.2.3.4", now=100.0)[0]
    assert bucket.take("1.2.3.4", now=100.0)[0]
    limited, retry = bucket.take("1.2.3.4", now=100.0)
    assert not limited
    assert retry > 0


def test_bucket_refills_over_time():
    bucket = _TokenBucketStore(capacity=1, refill_per_minute=1)
    assert bucket.take("ip", now=0.0)[0]
    assert not bucket.take("ip", now=0.0)[0]
    # 1 token/minute: 45s later only 0.75 tokens are available.
    allowed, retry = bucket.take("ip", now=45.0)
    assert not allowed and retry > 0
    allowed, _ = bucket.take("ip", now=61.0)
    assert allowed


def test_bucket_keys_are_isolated():
    bucket = _TokenBucketStore(capacity=1, refill_per_minute=60)
    assert bucket.take("a", now=0.0)[0]
    assert bucket.take("b", now=0.0)[0]
    assert not bucket.take("a", now=0.0)[0]


def test_middleware_returns_429_when_exhausted():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.ratelimit import RateLimitMiddleware as RLM

    app = FastAPI()
    app.add_middleware(RLM, capacity=1, refill_per_minute=0)

    @app.post("/query")
    def query():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/query", json={}).status_code == 200
    resp = client.post("/query", json={})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    # Other paths are never limited.
    assert client.get("/health").status_code == 200


# --- token usage accounting ----------------------------------------------


def test_usage_handler_accumulates_and_records():
    metrics.observe_tokens("m1", 100, 50)
    metrics.observe_tokens("m1", 10, 5)
    metrics.observe_tokens("m2", 7, 3)
    snap = metrics.snapshot()
    assert snap["tokens"]["m1"] == {
        "prompt_tokens": 110,
        "completion_tokens": 55,
        "calls": 2,
    }
    assert snap["tokens"]["m2"]["prompt_tokens"] == 7


def test_token_usage_handler_reads_llm_output():
    class FakeUsage(dict):
        pass

    class FakeResponse:
        llm_output = {"token_usage": {"prompt_tokens": 12, "completion_tokens": 8}}

    handler = TokenUsageHandler()
    handler.on_llm_end(FakeResponse())
    handler.on_llm_end(FakeResponse())
    assert handler.prompt_tokens == 24
    assert handler.completion_tokens == 16


def test_token_usage_handler_tolerates_missing_usage():
    class EmptyResponse:
        llm_output = None

    handler = TokenUsageHandler()
    handler.on_llm_end(EmptyResponse())
    assert handler.prompt_tokens == 0


# --- openTelemetry tracing ------------------------------------------------


def test_tracing_disabled_without_endpoint():
    """No OTLP endpoint configured: setup is a no-op and spans are safe."""
    from fastapi import FastAPI

    from app.tracing import setup_tracing, stage_span

    assert setup_tracing(FastAPI()) is False
    with stage_span("test_span") as span:
        if span is not None:
            span.set_attribute("k", "v")


def test_stage_span_records_when_sdk_active():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from app.tracing import get_tracer

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    with get_tracer().start_as_current_span("rag_stage") as span:
        span.set_attribute("docs.count", 4)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes["docs.count"] == 4
