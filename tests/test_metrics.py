"""In-process metrics: counters and latency percentiles (pure, no deps)."""

from app import metrics


def _reset():
    with metrics._lock:
        metrics._counters.clear()
        metrics._latencies.clear()


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
