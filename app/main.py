import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app import catalog, ingest, profiles, recommend
from app import feedback as feedback_store
from app.config import settings
from app.core.scheme import spine
from app.db import (
    VECTOR_GENERATION_COLUMN,
    VECTOR_TABLE,
    get_engine,
    stored_corpus_chunk_count,
    stored_corpus_generation,
    stored_embedding_model,
)
from app.ops import ops as operator
from app.ratelimit import RateLimitMiddleware
from app.tracing import setup_tracing
from app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    OpsAIRequest,
    OpsProviderRequest,
    ProfileCreateResponse,
    ProfileData,
    ProfileResponse,
    QueryRequest,
    QueryResponse,
    RecommendationRequest,
    RecommendationResponse,
)


def _require_admin(x_admin_token: str) -> None:
    """Shared admin guard for the ingestion and operator endpoints.

    Constant-time comparison against ``ADMIN_TOKEN``. When no token is
    configured these endpoints are *disabled* (503) rather than left open: an
    unauthenticated operator endpoint on a public deployment is how a demo
    becomes an incident. Tokens are never logged.
    """
    if not settings.admin_token.strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "This endpoint is disabled: no ADMIN_TOKEN is configured. "
                "Set ADMIN_TOKEN to enable operator controls."
            ),
        )
    if not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def count_vectors() -> int:
    with get_engine().connect() as conn:
        table_exists = conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{VECTOR_TABLE}"},
        ).scalar()
        if table_exists is None:
            return 0
        return int(
            conn.execute(text(f"SELECT count(*) FROM {VECTOR_TABLE}")).scalar()
        )


def count_generation_vectors(generation: str) -> int:
    """Rows belonging to one atomically activated corpus generation."""
    with get_engine().connect() as conn:
        return int(
            conn.execute(
                text(
                    f"SELECT count(*) FROM {VECTOR_TABLE} "
                    f"WHERE {VECTOR_GENERATION_COLUMN} = :generation"
                ),
                {"generation": generation},
            ).scalar()
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent on every startup: CREATE TABLE IF NOT EXISTS + empty-check.
    profiles.init_table()
    vectors = count_vectors()
    if vectors == 0:
        if settings.enable_auto_ingest:
            ingest.ingest()
    else:
        # Vectors exist: readiness rejects model or generation drift rather
        # than silently comparing embeddings from incompatible spaces.
        recorded = stored_embedding_model()
        if recorded is not None and recorded != settings.embedding_model:
            logging.getLogger(__name__).warning(
                "Vector store embedding model does not match configuration. "
                "Run: python scripts/reembed.py"
            )
    if vectors > 0 or settings.enable_auto_ingest:
        from app.db import ensure_fts_index

        ensure_fts_index()
    yield


app = FastAPI(title="SchemeGPT", lifespan=lifespan)

# OpenTelemetry: no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is configured.
setup_tracing(app)

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
app.add_middleware(RateLimitMiddleware)


@app.get("/livez", include_in_schema=False)
def livez():
    """Process liveness probe: intentionally performs no dependency I/O."""
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    """Dependency readiness for safe traffic routing and post-deploy checks."""
    checks: dict[str, object] = {"database": "ok"}
    try:
        vectors = count_vectors()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Readiness database check failed (%s).", type(exc).__name__
        )
        checks["database"] = "unavailable"
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        ) from None

    checks["vectors"] = vectors
    if vectors < 1:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )

    recorded_model = stored_embedding_model()
    if recorded_model != settings.embedding_model:
        checks["embedding_model"] = "mismatch"
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )

    checks["embedding_model"] = "ok"
    try:
        generation = stored_corpus_generation()
        expected_count = stored_corpus_chunk_count()
        generation_count = (
            count_generation_vectors(generation) if generation else 0
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Readiness generation check failed (%s).", type(exc).__name__
        )
        checks["database"] = "unavailable"
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        ) from None
    if (
        not generation
        or expected_count != vectors
        or generation_count != vectors
    ):
        checks["corpus_generation"] = "incomplete"
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )

    checks["corpus_generation"] = "ok"
    return {
        "status": "ready",
        "mode": "live" if settings.groq_api_key.strip() else "demo",
        "checks": checks,
    }


@app.get("/health")
def health():
    """Liveness, plus a safe summary of operator state.

    Deliberately still ``ok`` while AI generation is switched off or the
    provider circuit is open: the service is up and serving retrieval-only
    answers. That is an operator decision, not an outage — and the container
    healthcheck must not restart the API because a human pressed the kill
    switch. Pod/platform alerting should watch the ``ai`` and
    ``provider_circuit`` fields instead.
    """
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "ai": "enabled" if operator.ai_enabled else "disabled",
        "provider_circuit": operator.breaker.state,
    }


@app.post("/ingest")
def ingest_docs(x_admin_token: str = Header(default="")):
    """Re-ingest Markdown sources into the vector store (admin only).

    Protected by the ``X-Admin-Token`` header, compared in constant time with
    the configured ``ADMIN_TOKEN``. When no ``ADMIN_TOKEN`` is configured the
    endpoint is disabled with a clear 503 response: manual re-ingestion must
    not be exposed publicly. Startup auto-ingestion is controlled by
    ``ENABLE_AUTO_INGEST`` and runs
    (idempotently) when enabled and the vector store is empty. Tokens are
    never logged.
    """
    _require_admin(x_admin_token)
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
        **spine.egress(
            req.question,
            language=req.language,
            profile=req.profile,
        )
    )


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(req: FeedbackRequest):
    """Record a thumbs-up/down rating on one answer.

    Ratings feed the offline eval set (curated thumbs-up cases grow the
    regression suite). No profile data or identifiers are accepted here.
    """
    stored = feedback_store.record_feedback(
        question=req.question,
        answer=req.answer,
        rating=req.rating,
        language=req.language,
        comment=req.comment,
    )
    return FeedbackResponse(stored=stored)


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    """Streamed variant of /query over Server-Sent Events.

    Same request schema and bounds; events: sources -> token* -> done|error.
    Demo fallback semantics are identical to /query: labelled, HTTP 200,
    never a traceback.
    """
    import time as _time

    from app import metrics

    start = _time.perf_counter()

    async def _proxy():
        try:
            async for part in spine.stream(
                req.question, req.language, req.profile
            ):
                yield part
        finally:
            metrics.observe_latency((_time.perf_counter() - start) * 1000)

    return StreamingResponse(
        _proxy(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Operator control plane (field) ------------------------------------------
# See app/ops.py. These are the controls an engineer uses *after* go-live:
# stop generation, route to another provider endpoint, see why answers are
# degraded. Control endpoints require ADMIN_TOKEN; the read-only status
# endpoint is public and safe (no secrets, no audit reasons, masked URLs).


@app.get("/ops/status")
def ops_status():
    """Operator snapshot: AI switch, provider circuit breaker, degraded counts.

    Safe to expose publicly: it carries states and counters only. Provider
    error *types* are included (``RateLimitError``), provider error text is
    not, and the endpoint URL is masked to scheme://host/path with any userinfo
    or query string removed.
    """
    return operator.status()


@app.get("/ops/audit")
def ops_audit(x_admin_token: str = Header(default="")):
    """Operator action trail, newest last (admin only).

    Admin-only because a disable reason is written during an incident and can
    name a customer, a person, or a ticket — useful to an operator, not
    something to publish on a status endpoint.
    """
    _require_admin(x_admin_token)
    return {"audit": operator.audit()}


@app.post("/ops/ai")
def ops_set_ai(payload: OpsAIRequest, x_admin_token: str = Header(default="")):
    """Turn AI generation on or off for this instance (admin only).

    Off means retrieval-only answers: the service stays up, keeps citing real
    source documents, and stops calling the model. The decision is persisted to
    ``OPS_STATE_FILE``, so it survives a restart or a redeploy — and it is
    recorded in the audit trail with the actor and reason.
    """
    _require_admin(x_admin_token)
    if payload.enabled:
        return operator.enable_ai(actor=payload.actor, reason=payload.reason)
    return operator.disable_ai(reason=payload.reason, actor=payload.actor)


@app.post("/ops/provider")
def ops_set_provider(
    payload: OpsProviderRequest, x_admin_token: str = Header(default="")
):
    """Repoint the LLM client at another endpoint, or clear the override.

    This is the "route our traffic through your gateway" control: an operator
    can send generation through the customer's egress proxy or a secondary
    provider without a rebuild or redeploy. Applied in memory and not written to
    disk — the durable form is ``GROQ_API_BASE`` in the environment, so an
    endpoint can never be changed permanently by someone with API access alone.
    """
    _require_admin(x_admin_token)
    try:
        state = operator.set_provider_base_url(
            payload.base_url, actor=payload.actor, reason=payload.reason
        )
    except ValueError as exc:
        # Safe by construction: the validator never echoes the URL back.
        raise HTTPException(status_code=400, detail=str(exc)) from None
    # No chain/client cache to invalidate: ``build_answer_chain`` constructs a
    # fresh LLM client from the current override on every request, so the new
    # endpoint takes effect on the next request without a restart.
    return state


@app.get("/metrics")
def metrics_endpoint():
    """Aggregate in-process counters + latency percentiles (no per-request data,
    no PII — safe to expose)."""
    from app import metrics

    return metrics.snapshot()
