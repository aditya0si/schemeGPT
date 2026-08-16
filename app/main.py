import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app import catalog, ingest, profiles, recommend
from app.config import settings
from app.db import COLLECTION_NAME, get_engine
from app.rag import answer
from app.stream import stream_answer
from app.schemas import (
    ProfileCreateResponse,
    ProfileData,
    ProfileResponse,
    QueryRequest,
    QueryResponse,
    RecommendationRequest,
    RecommendationResponse,
)


def count_vectors() -> int:
    with get_engine().connect() as conn:
        table_exists = conn.execute(
            text("SELECT to_regclass('public.langchain_pg_collection')")
        ).scalar()
        if table_exists is None:
            return 0
        return int(
            conn.execute(
                text(
                    "SELECT count(*) FROM langchain_pg_embedding e "
                    "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                    "WHERE c.name = :name"
                ),
                {"name": COLLECTION_NAME},
            ).scalar()
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent on every startup: CREATE TABLE IF NOT EXISTS + empty-check.
    profiles.init_table()
    if count_vectors() == 0:
        ingest.ingest()
    yield


app = FastAPI(title="SchemeGPT", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/ingest")
def ingest_docs(x_admin_token: str = Header(default="")):
    """Re-ingest Markdown sources into the vector store (admin only).

    Protected by the ``X-Admin-Token`` header, compared in constant time with
    the configured ``ADMIN_TOKEN``. When no ``ADMIN_TOKEN`` is configured the
    endpoint is disabled with a clear 503 response: manual re-ingestion must
    not be exposed publicly. Startup auto-ingestion is unchanged and still runs
    (idempotently) when the vector store is empty. Tokens are never logged.
    """
    if not settings.admin_token.strip():
        raise HTTPException(
            status_code=503,
            detail="Ingestion is disabled: no ADMIN_TOKEN is configured.",
        )
    if not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(
            status_code=401, detail="Invalid admin token."
        )
    return {"chunks": ingest.ingest()}


@app.get("/coverage")
def coverage():
    """Coverage transparency: what the catalog actually contains.

    Pure report over the local data files (``data/india_states.json`` and
    ``data/scheme_catalog.json``): 36 jurisdictions (28 states + 8 UTs), the
    catalog totals split by ``data_status``, per-jurisdiction status/counts,
    and a truthful ``coverage_note``. No claim is made that all government
    schemes have been ingested.
    """
    return catalog.coverage_summary()


@app.get("/states")
def list_states():
    """Nationwide state/UT discovery directory, in stable catalog order.

    Records are ``directory_seed`` entries linking to the official national
    MyScheme discovery portal; they are not verified eligibility decisions.
    """
    return catalog.load_states_catalog()


@app.post("/profiles", response_model=ProfileCreateResponse)
def create_profile(payload: ProfileData):
    """Create a saved profile.

    The raw ``access_token`` is returned only here (exactly once). Only its
    SHA-256 hash is stored; the token is required for all later
    read/update/delete calls via the ``X-Profile-Token`` header.
    """
    return ProfileCreateResponse(**profiles.create_profile(payload.model_dump()))


@app.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, x_profile_token: str = Header(...)):
    record = profiles.get_profile(profile_id, x_profile_token)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Profile not found or token invalid"
        )
    return ProfileResponse(
        profile_id=record["profile_id"],
        profile=ProfileData(**record["profile"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@app.put("/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: str, payload: ProfileData, x_profile_token: str = Header(...)
):
    record = profiles.update_profile(profile_id, x_profile_token, payload.model_dump())
    if record is None:
        raise HTTPException(
            status_code=404, detail="Profile not found or token invalid"
        )
    return ProfileResponse(
        profile_id=record["profile_id"],
        profile=ProfileData(**record["profile"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@app.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, x_profile_token: str = Header(...)):
    if not profiles.delete_profile(profile_id, x_profile_token):
        raise HTTPException(
            status_code=404, detail="Profile not found or token invalid"
        )
    return {"status": "deleted", "profile_id": profile_id}


@app.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(req: RecommendationRequest):
    """Deterministic starter recommendations.

    No LLM is called in this iteration. Central schemes are ranked from
    ``data/scheme_catalog.json`` using simple profile signals, and the matching
    state/UT directory seed is included when a state is selected. The
    ``language`` field localizes ``reason``/``benefits_or_scope`` (and the
    disclaimer) to Hindi when set to ``"hi"``.
    """
    return recommend.build_recommendations(req.profile, language=req.language)


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """Ask a real-life question, optionally in Hindi and with a saved profile.

    ``language`` selects the answer language and ``profile`` attaches a saved
    citizen profile that the chain may use only to tailor guidance. No access
    tokens or profile secrets are ever accepted, logged, or returned here.
    """
    return QueryResponse(
        **answer(
            req.question,
            language=req.language,
            profile=req.profile,
        )
    )


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    """Streamed variant of /query over Server-Sent Events.

    Same request schema and bounds; events: sources -> token* -> done|error.
    Demo fallback semantics are identical to /query: labelled, HTTP 200,
    never a traceback.
    """
    return StreamingResponse(
        stream_answer(req.question, req.language, req.profile),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
