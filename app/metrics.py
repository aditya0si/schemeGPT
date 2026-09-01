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
_token_usage: dict[str, dict[str, int]] = {}


def observe_tokens(model: str, prompt: int, completion: int) -> None:
    """Accumulate LLM token usage per model (from response usage metadata)."""
    with _lock:
        bucket = _token_usage.setdefault(
            model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        )
        bucket["prompt_tokens"] += prompt
        bucket["completion_tokens"] += completion
        bucket["calls"] += 1


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
    snapshot_out: dict[str, Any] = {
        "counters": counters,
        "latency_ms": {
            "count": len(values),
            "mean": mean,
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
        },
    }
    hits = counters.get("cache_hit", 0)
    misses = counters.get("cache_miss", 0)
    lookups = hits + misses
    snapshot_out["cache"] = {
        "hit_rate": round(hits / lookups, 4) if lookups else None,
        "hits": hits,
        "misses": misses,
    }
    with _lock:
        snapshot_out["tokens"] = {
            model: dict(bucket) for model, bucket in _token_usage.items()
        }
    return snapshot_out
