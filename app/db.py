import asyncio
import logging
import sys
from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_postgres import Column, PGEngine, PGVectorStore
from sqlalchemy import create_engine, text

from app.config import settings
from app.embeddings import build_embeddings

logger = logging.getLogger(__name__)


def _ensure_windows_selector_event_loop_policy() -> None:
    """Run psycopg3's async I/O on a selector loop on Windows.

    ``langchain_postgres.PGEngine`` (via ``get_pg_engine``) drives SQLAlchemy's
    async engine with the psycopg3 async driver. psycopg3 refuses Windows'
    default ``ProactorEventLoop`` and raises::

        Psycopg cannot use the 'ProactorEventLoop' to run in async mode.

    That breaks ingestion in :func:`ensure_vector_table` and retrieval in
    :func:`get_vectorstore` (``similarity_search_with_score``). Linux and the
    containers already default to a selector loop, so this guard is Windows-only
    and leaves other platforms byte-for-byte unchanged. It runs at import time,
    before any async ``PGEngine`` connection can be created; that also covers a
    server started with ``uvicorn app.main:app``, whose loop is built from the
    policy after this module is imported. Idempotent: a policy that is already
    the selector policy is left untouched.

    Verified with:
        ./.venv/Scripts/python.exe -m pytest tests/test_db.py -q
    """
    if sys.platform != "win32":
        return
    policy = asyncio.get_event_loop_policy()
    if not isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_ensure_windows_selector_event_loop_policy()

# The maintained adapter uses an application-owned table instead of the legacy
# langchain_pg_collection/langchain_pg_embedding schema. Existing deployments
# can re-ingest beside the old tables without mutating or deleting them.
VECTOR_TABLE = "scheme_docs_v2"
VECTOR_ID_COLUMN = "chunk_id"
VECTOR_METADATA_COLUMN = "metadata"
VECTOR_GENERATION_COLUMN = "corpus_generation"
VECTOR_MODEL_TABLE = "scheme_docs_vector_metadata"


class CorpusMetadataError(RuntimeError):
    """The active corpus metadata exists but could not be read.

    Raised by the strict readers so a database failure is never mistaken for an
    uninitialized corpus (which would otherwise disable generation binding and
    fail open onto an unbound retrieval).
    """


def _database_url_for_psycopg(url: str) -> str:
    """Normalize legacy Postgres URLs to SQLAlchemy's psycopg3 driver."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache
def get_embeddings() -> Embeddings:
    """Embeddings for the configured backend, E5-prefixed when required.

    Which runtime runs the model is a deployment decision (EMBEDDING_BACKEND):
    PyTorch for local work, ONNX Runtime for the free-tier image that cannot
    hold PyTorch plus the fp32 checkpoint inside 512 MB. The corpus and the
    queries must be embedded by the same backend, or they land in slightly
    different vector spaces.
    """
    return build_embeddings(settings.embedding_model, settings.embedding_backend)


@lru_cache
def get_engine():
    """Synchronous SQLAlchemy engine used by operational and FTS queries."""
    return create_engine(_database_url_for_psycopg(settings.database_url))


@lru_cache
def get_pg_engine() -> PGEngine:
    """Async-backed engine required by the maintained PGVectorStore adapter."""
    return PGEngine.from_connection_string(
        _database_url_for_psycopg(settings.database_url)
    )


def _vector_table_exists() -> bool:
    with get_engine().connect() as conn:
        return conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{VECTOR_TABLE}"},
        ).scalar() is not None


@lru_cache
def _embedding_dimension() -> int:
    """Discover the configured embedding width instead of hard-coding a model."""
    return len(get_embeddings().embed_query("dimension probe"))


def ensure_vector_table(vector_size: int | None = None) -> None:
    """Create the application vector table, tolerating concurrent first use."""
    engine = get_pg_engine()
    if _vector_table_exists():
        return
    try:
        engine.init_vectorstore_table(
            table_name=VECTOR_TABLE,
            vector_size=vector_size or _embedding_dimension(),
            id_column=Column(VECTOR_ID_COLUMN, "VARCHAR", nullable=False),
            metadata_json_column=VECTOR_METADATA_COLUMN,
            metadata_columns=[
                Column(VECTOR_GENERATION_COLUMN, "VARCHAR", nullable=False)
            ],
            overwrite_existing=False,
        )
    except Exception:
        # A second worker may create the table after our existence check.
        # Suppress only that verified race; propagate every other failure.
        if not _vector_table_exists():
            raise


@lru_cache
def get_vectorstore() -> PGVectorStore:
    """Open the application-owned pgvector table through PGVectorStore."""
    ensure_vector_table()
    return PGVectorStore.create_sync(
        engine=get_pg_engine(),
        embedding_service=get_embeddings(),
        table_name=VECTOR_TABLE,
        id_column=VECTOR_ID_COLUMN,
        metadata_json_column=VECTOR_METADATA_COLUMN,
        metadata_columns=[VECTOR_GENERATION_COLUMN],
    )


def _write_vector_metadata(connection: Any, values: dict[str, str]) -> None:
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {VECTOR_MODEL_TABLE} ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {VECTOR_MODEL_TABLE} (key, value) "
            "VALUES (:key, :value) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        ),
        [{"key": key, "value": value} for key, value in values.items()],
    )


def record_corpus_state(
    *,
    model_name: str,
    generation: str,
    chunk_count: int,
    connection: Any | None = None,
) -> None:
    """Persist active corpus metadata, optionally inside a caller transaction."""
    values = {
        "embedding_model": model_name,
        "corpus_generation": generation,
        "corpus_chunk_count": str(chunk_count),
    }
    if connection is not None:
        _write_vector_metadata(connection, values)
        return
    with get_engine().begin() as conn:
        _write_vector_metadata(conn, values)


def _stored_vector_metadata(key: str, *, strict: bool = False) -> str | None:
    try:
        with get_engine().connect() as conn:
            table_exists = conn.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": f"public.{VECTOR_MODEL_TABLE}"},
            ).scalar()
            if table_exists is None:
                return None
            return conn.execute(
                text(
                    f"SELECT value FROM {VECTOR_MODEL_TABLE} WHERE key = :key"
                ),
                {"key": key},
            ).scalar()
    except Exception as exc:
        logger.warning("Could not read vector metadata key %s.", key)
        if strict:
            # A database failure is distinct from a genuinely absent value:
            # callers that must not fail open need to see it.
            raise CorpusMetadataError(
                f"Could not read vector metadata key '{key}'."
            ) from exc
        return None


def stored_embedding_model() -> str | None:
    """The embedding model recorded for this vector table, or None if unknown."""
    return _stored_vector_metadata("embedding_model")


def stored_corpus_generation() -> str | None:
    """The atomically activated corpus generation, or None if unknown."""
    return _stored_vector_metadata("corpus_generation")


def read_corpus_generation() -> str | None:
    """Strict active-generation read for generation-binding callers.

    Returns ``None`` only when the metadata table or key is genuinely absent
    (an uninitialized corpus). A database failure raises
    :class:`CorpusMetadataError` instead of being silently reported as unknown,
    so generation binding fails closed rather than open.
    """
    return _stored_vector_metadata("corpus_generation", strict=True)


def stored_corpus_chunk_count() -> int | None:
    """Expected row count for the active corpus generation."""
    value = _stored_vector_metadata("corpus_chunk_count")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


@lru_cache
def _default_retriever():
    """Shared unbound hybrid retriever (searches the whole active table)."""
    from app.retrieval import HybridRetriever

    return HybridRetriever()


def get_retriever(corpus_generation: str | None = None):
    """Hybrid retriever used by both synchronous and streaming query APIs.

    Passing ``corpus_generation`` returns a retriever pinned to that generation
    so retrieval, cache lookup, and cache store all observe the same corpus.
    """
    if corpus_generation is None:
        return _default_retriever()
    from app.retrieval import HybridRetriever

    return HybridRetriever(corpus_generation=corpus_generation)


def fetch_generation_documents(
    generation: str, *, source: str | None = None
) -> list[dict]:
    """Answer context read from one generation-pinned corpus.

    Returns ``{"content", "metadata"}`` rows from the vector table filtered to
    ``generation`` (optionally to one ``source`` file). Agentic tools use this
    instead of the filesystem so a locally edited or deleted Markdown file can
    never be mixed into an answer bound to an earlier database generation.
    """
    if not generation:
        raise ValueError("fetch_generation_documents requires a corpus generation")
    where = f"{VECTOR_GENERATION_COLUMN} = :generation"
    params: dict[str, object] = {"generation": generation}
    if source is not None:
        where += (
            f" AND ({VECTOR_METADATA_COLUMN} ->> 'source' = :source"
            f" OR {VECTOR_METADATA_COLUMN} ->> 'source' LIKE :source_suffix)"
        )
        params["source"] = source
        params["source_suffix"] = f"%/{source}"
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT content, {VECTOR_METADATA_COLUMN} FROM {VECTOR_TABLE} "
                f"WHERE {where} "
                f"ORDER BY ({VECTOR_METADATA_COLUMN} ->> 'source'), "
                f"({VECTOR_METADATA_COLUMN} ->> 'chunk_index')::int"
            ),
            params,
        ).fetchall()
    return [{"content": row[0], "metadata": row[1] or {}} for row in rows]


def fetch_generation_jurisdictions(generation: str) -> list[str]:
    """Jurisdiction names present in one generation-pinned corpus, sorted."""
    if not generation:
        raise ValueError("fetch_generation_jurisdictions requires a corpus generation")
    jurisdiction = f"{VECTOR_METADATA_COLUMN} ->> 'jurisdiction'"
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT DISTINCT {jurisdiction} AS jurisdiction "
                f"FROM {VECTOR_TABLE} "
                f"WHERE {VECTOR_GENERATION_COLUMN} = :generation "
                f"AND {jurisdiction} IS NOT NULL "
                "ORDER BY jurisdiction"
            ),
            {"generation": generation},
        ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def _ensure_fts_index(connection: Any) -> None:
    """Add the full-text column/index using an already-open connection."""
    connection.execute(
        text(
            f"ALTER TABLE {VECTOR_TABLE} "
            "ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
        )
    )
    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS idx_{VECTOR_TABLE}_tsv "
            f"ON {VECTOR_TABLE} USING GIN (tsv)"
        )
    )


def ensure_fts_index(connection: Any | None = None) -> None:
    """Idempotently add the full-text search column and GIN index.

    When ``connection`` is provided the DDL runs inside the caller's
    transaction, so ingestion can activate the corpus and its FTS index
    atomically under the same advisory lock. Otherwise a short transaction is
    opened here (startup readiness path).
    """
    if connection is not None:
        _ensure_fts_index(connection)
        return
    with get_engine().begin() as conn:
        _ensure_fts_index(conn)
