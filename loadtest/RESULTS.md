# Load test — SSE streaming endpoint

Tool: Locust (`loadtest/locustfile.py`). The streamed request reads the full
SSE event sequence (`sources → token* → done`) and fails a request unless the
terminal `done` event arrives — so a "success" is a complete, well-formed
answer stream, not just an HTTP 200.

## Serving-layer numbers (2026-09-01, Windows dev machine, CPU-only)

Stack under test: full FastAPI app in demo mode (no LLM call) — this measures
*our* serving layer: SSE plumbing, rate limiting middleware, serialization.
Live answers are dominated by Groq inference latency and its shared free-tier
limits, which no amount of local engineering removes.

| Metric | Value |
| --- | --- |
| Concurrent users | 25 |
| Duration | 60 s |
| Stream requests completed | 860 |
| Failures | 0 (0.00 %) |
| Throughput | 14.5 streams/s (19.05 req/s incl. health checks) |
| Median latency | 11 ms |
| p95 | 25 ms |
| p99 | 51 ms |

Reproduce:

```bash
GROQ_API_KEY= RATE_LIMIT_RPM=0 uvicorn app.main:app --port 8001
locust -f loadtest/locustfile.py --host http://127.0.0.1:8001 \
       --users 25 --spawn-rate 5 --run-time 60s --headless --only-summary
```

With the rate limiter enabled (`RATE_LIMIT_RPM=20`, the default), sustained
load above 20 req/min per IP receives HTTP 429 + `Retry-After` — by design,
to protect the shared Groq quota.
