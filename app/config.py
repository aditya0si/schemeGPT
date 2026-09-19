from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    groq_api_key: str = ""
    database_url: str = "postgresql+psycopg2://scheme:scheme@localhost:5432/schemegpt"
    embedding_model: str = "intfloat/multilingual-e5-small"
    groq_model: str = "openai/gpt-oss-120b"
    # Small, fast model for cheap sub-tasks (normalization, routing).
    groq_fast_model: str = "openai/gpt-oss-20b"
    # Optional cross-encoder rerank stage (BAAI/bge-reranker-base, ~2 GB on
    # CPU). Keep OFF on small free-tier VPSes; retrieval still fuses vector +
    # full-text without it.
    enable_reranker: bool = False
    # Semantic query cache (pgvector-backed). Serves stored live answers for
    # paraphrased repeats of a question (cosine >= 0.95, same language and
    # profile). Disable with ENABLE_SEMANTIC_CACHE=false.
    enable_semantic_cache: bool = True
    # Per-IP token-bucket rate limit for /query and /query/stream (requests
    # per minute; 0 disables). Protects the shared Groq free-tier quota.
    rate_limit_rpm: int = 20
    # OpenTelemetry OTLP endpoint (e.g. http://localhost:4318). Leave blank to
    # disable tracing entirely (zero overhead no-op spans).
    otel_exporter_otlp_endpoint: str = ""
    # Judge model for the RAGAS eval harness. Defaults to the answer model;
    # override (e.g. the smaller fast model) to fit an eval run inside a
    # separate per-model daily-token bucket on the free tier.
    eval_judge_model: str = ""
    data_dir: str = "data/schemes"
    # Admin token required for POST /ingest via the X-Admin-Token header.
    # Leave blank to disable manual re-ingestion (startup auto-ingestion is
    # unchanged and still runs when the vector store is empty).
    admin_token: str = ""
    # Comma-separated list of browser origins allowed by CORS. The Streamlit
    # web UI talks to the API server-side (no browser CORS), so only origins
    # that open the API directly from a browser need to be listed. Defaults to
    # the local Streamlit dev origins.
    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    # --- Field / operator controls (see app/ops.py) ----------------------
    # Initial AI generation state. The runtime kill switch (POST /ops/ai)
    # persists to OPS_STATE_FILE and overrides this value on restart, so an
    # operator decision survives a redeploy.
    ops_ai_enabled: bool = True
    # Durable operator state (kill switch). Relative paths resolve against the
    # repository root; point this at a mounted volume to survive container
    # replacement (see docs/FIELD-DEPLOY.md).
    ops_state_file: str = "var/ops_state.json"
    # Optional provider endpoint override: route LLM traffic through the
    # customer's API gateway / egress proxy, or a secondary provider.
    # Example: GROQ_API_BASE=https://llm-gw.customer.internal/groq/v1
    groq_api_base: str = ""
    # Circuit breaker: open after this many consecutive provider failures and
    # stop calling a provider that is already failing; one probe after the
    # cooldown decides whether to close.
    breaker_failure_threshold: int = 3
    breaker_reset_timeout_s: float = 30.0
    # Build identity reported by GET /ops/status (set at image build time from
    # the deployed commit; see deploy/field/).
    git_sha: str = ""

    # --- Provider call bounds -------------------------------------------
    # Measured, not guessed: with the defaults the SDK applies (no timeout, two
    # retries with backoff), a provider that accepts the connection and then
    # goes silent left a citizen request hanging for ~150s before the fallback
    # ran. A helpdesk answer that takes two and a half minutes is worse than a
    # degraded answer that takes twenty seconds, so the call is bounded here and
    # the circuit breaker does the rest.
    groq_timeout_s: float = 20.0
    groq_max_retries: int = 0

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        # A deployment's .env is not ours alone: customers and the field kit add
        # their own keys (proxies, deployment pins, site labels). pydantic-settings
        # defaults to rejecting unknown keys, which turns an unrelated variable
        # into a startup crash — that is a data-plane outage caused by config
        # hygiene. Unknown keys are ignored here on purpose.
        extra="ignore",
    )


settings = Settings()


def data_dir_path() -> Path:
    return ROOT_DIR / settings.data_dir
