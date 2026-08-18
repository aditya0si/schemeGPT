"""Lightweight in-process observability: counters + latency percentiles.

Counters and latencies are thread-safe (GIL + lock) and hold only aggregates —
never question text, profile data, or other PII — so ``GET /metrics`` is safe
to expose. Percentiles are computed over a bounded rolling window (no numpy).
"""

import threading
import time
from collections import deque
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = {}
_latencies: deque = deque(maxlen=500)


def inc(name: str, delta: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + delta


def observe_latency(ms: float) -> None:
    with _lock:
        _latencies.append(ms)


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return round(sorted_values[index], 3)


def snapshot() -> dict[str, Any]:
    with _lock:
        counters = dict(_counters)
        values = sorted(_latencies)
    mean = round(sum(values) / len(values), 3) if values else None
    return {
        "counters": counters,
        "latency_ms": {
            "count": len(values),
            "mean": mean,
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
        },
    }
