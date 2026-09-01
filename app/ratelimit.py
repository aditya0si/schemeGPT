"""Per-IP token-bucket rate limiting for the query endpoints.

The free-tier Groq quota (requests/minute and tokens/minute) is shared across
all users of a deployment, so a single client hammering /query degrades the
service for everyone. This middleware gives every client IP a token bucket:
``capacity`` tokens, refilled at ``refill_per_minute``. An empty bucket means
HTTP 429 with a Retry-After hint; nothing else about the request changes.

Backend: an in-process dict guarded by a lock (correct for a single uvicorn
worker, which is how the API container runs). For horizontal scaling, swap
``_TokenBucketStore`` for a Redis-backed implementation — the middleware only
needs ``take(ip) -> bool``.

Question text and profile data are never logged or stored here: the key is
the client IP, which is the minimum needed to rate-limit fairly.
"""

from __future__ import annotations

import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.metrics import inc

QUERY_PATHS = {"/query", "/query/stream"}


class _TokenBucketStore:
    def __init__(self, capacity: float, refill_per_minute: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, ts)
        self._lock = threading.Lock()

    def take(self, ip: str, now: float | None = None) -> tuple[bool, float]:
        """Try to take one token. Returns (allowed, seconds_until_retry)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get(ip, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
            if tokens >= 1.0:
                self._buckets[ip] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[ip] = (tokens, now)
            if self.refill_per_second <= 0:
                # No refill configured: an exhausted bucket waits a long time.
                return False, 3600.0
            return False, (1.0 - tokens) / self.refill_per_second


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket limiter for /query*; other paths pass through untouched."""

    def __init__(self, app, capacity: int | None = None, refill_per_minute: int | None = None):
        super().__init__(app)
        # A capacity equal to the per-minute refill allows short bursts
        # without letting a client exceed its steady-state share.
        rpm = refill_per_minute if refill_per_minute is not None else settings.rate_limit_rpm
        self.store = _TokenBucketStore(capacity or rpm, rpm)

    async def dispatch(self, request, call_next):
        if request.url.path not in QUERY_PATHS or request.method != "POST":
            return await call_next(request)
        if settings.rate_limit_rpm <= 0:
            return await call_next(request)  # disabled explicitly
        allowed, retry_after = self.store.take(_client_ip(request))
        if allowed:
            return await call_next(request)
        inc("rate_limited_total")
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down and retry."},
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )
