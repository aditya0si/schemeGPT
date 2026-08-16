"""Development stub API for frontend work without Docker/pgvector.

Serves /health, /coverage, and /query/stream (forced DEMO mode) from the real
app modules with no database and no lifespan. Demo answers come from the real
``app.rag.demo_answer`` over ``data/demo_responses.json``.

Usage:  .venv/Scripts/python.exe scripts/dev_stub_api.py [port]
The stub prints a line when ready. Not part of the production image.
"""

import sys
from pathlib import Path

# Direct invocation (`python scripts/dev_stub_api.py`) must see the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

# Force demo mode regardless of the developer's .env key: the stub has no
# database, so the live path could never work here anyway.
from app.config import settings

settings.groq_api_key = ""

from app import catalog  # noqa: E402  (import after settings override)
from app.schemas import QueryRequest  # noqa: E402
from app.stream import stream_answer  # noqa: E402

app = FastAPI(title="SchemeGPT dev stub")


@app.get("/health")
def health():
    return {"status": "ok", "mode": "dev-stub"}


@app.get("/coverage")
def coverage():
    return catalog.coverage_summary()


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    return StreamingResponse(
        stream_answer(req.question, req.language, req.profile),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    print(f"dev stub API on http://localhost:{port} (demo mode)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
