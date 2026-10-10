"""In-process metrics: counters and latency percentiles (pure, no deps)."""

import pytest

from app import metrics, pricing


def _reset():
    with metrics._lock:
        metrics._counters.clear()
        metrics._latencies.clear()
        metrics._token_usage.clear()
        metrics._cost_by_model.clear()
        metrics._cost_unpriced_calls = 0
    with pricing._lock:
        pricing._unpriced.clear()


def test_counters_accumulate():
    _reset()
    metrics.inc("a")
    metrics.inc("a")
    metrics.inc("b")
    snap = metrics.snapshot()
    assert snap["counters"]["a"] == 2
    assert snap["counters"]["b"] == 1


def test_latency_percentiles_and_mean():
    _reset()
    for value in [10, 20, 30, 40, 100]:
        metrics.observe_latency(value)
    snap = metrics.snapshot()
    lat = snap["latency_ms"]
    assert lat["count"] == 5
    assert lat["mean"] == 40.0
    assert lat["p50"] == 30.0   # int(5*0.5)=2 -> sorted[2]
    assert lat["p95"] == 100.0  # int(5*0.95)=4 -> sorted[4]


def test_empty_snapshot_is_safe():
    _reset()
    snap = metrics.snapshot()
    assert snap["counters"] == {}
    assert snap["latency_ms"]["count"] == 0
    assert snap["latency_ms"]["mean"] is None
    assert snap["latency_ms"]["p95"] is None


# --- cost ledger ----------------------------------------------------------


def test_known_model_cost_appears_in_by_model_and_total():
    _reset()
    model = "openai/gpt-oss-120b"
    metrics.observe_tokens(model, 1_000_000, 1_000_000)
    snap = metrics.snapshot()
    assert snap["cost"]["by_model"][model] == pytest.approx(0.75)
    assert snap["cost"]["total"] == pytest.approx(0.75)
    assert snap["cost"]["unpriced_calls"] == 0


def test_unpriced_model_counts_call_but_not_cost():
    _reset()
    metrics.observe_tokens("openai/gpt-oss-120b", 1_000_000, 0)  # $0.15
    metrics.observe_tokens("acme/unpriced", 1_000_000, 1_000_000)
    snap = metrics.snapshot()
    assert snap["cost"]["total"] == pytest.approx(0.15)
    assert snap["cost"]["unpriced_calls"] == 1
    assert "acme/unpriced" not in snap["cost"]["by_model"]


def test_per_request_avg_none_before_calls_then_correct_after():
    _reset()
    assert metrics.snapshot()["cost"]["per_request_avg"] is None
    metrics.observe_tokens("openai/gpt-oss-120b", 1_000_000, 1_000_000)  # $0.75
    metrics.observe_tokens("openai/gpt-oss-120b", 1_000_000, 0)  # $0.15
    snap = metrics.snapshot()
    assert snap["cost"]["total"] == pytest.approx(0.90)
    assert snap["cost"]["per_request_avg"] == pytest.approx(0.45)


def test_snapshot_top_level_keys_are_additive():
    _reset()
    assert set(metrics.snapshot()) == {
        "counters",
        "latency_ms",
        "cache",
        "tokens",
        "cost",
    }


def test_metrics_endpoint_keeps_existing_keys_and_adds_cost():
    from fastapi.testclient import TestClient

    import app.main as main

    _reset()
    metrics.observe_tokens("openai/gpt-oss-120b", 1_000_000, 0)
    body = TestClient(main.app).get("/metrics").json()
    assert {"counters", "latency_ms", "cache", "tokens", "cost"} <= set(body)
    assert body["cost"]["total"] == pytest.approx(0.15)
