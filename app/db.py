import json
import logging
from functools import lru_cache

from langchain_community.vectorstores import PGVector
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy import create_engine, text

from app.config import settings
from app.embeddings import E5PrefixEmbeddings, needs_e5_prefixes

logger = logging.getLogger(__name__)

COLLECTION_NAME = "scheme_docs"


@lru_cache
def get_embeddings() -> Embeddings:
    """Local embeddings, E5-prefixed when the model follows the convention."""
    inner: Embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    if needs_e5_prefixes(settings.embedding_model):
        return E5PrefixEmbeddings(inner)
    return inner


@lru_cache
def get_engine():
    return create_engine(settings.database_url)


@lru_cache
def get_vectorstore() -> PGVector:
    return PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=settings.database_url,
        embedding_function=get_embeddings(),
        pre_delete_collection=False,
    )


def record_embedding_model(model_name: str) -> None:
    """Persist the embedding model used for this collection's vectors.

    Stored in the collection's cmetadata so startup can detect a model change
    (vectors embedded by a different model are silently wrong until re-embedded).
    Failures are logged and never fatal: ingestion must not break because a
    metadata write failed.
    """
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "UPDATE langchain_pg_collection "
                    "SET cmetadata = :meta WHERE name = :name"
                ),
                {
                    "meta": json.dumps({"embedding_model": model_name}),
                    "name": COLLECTION_NAME,
                },
            )
    except Exception:
        logger.warning("Could not record embedding model metadata.", exc_info=True)


def stored_embedding_model() -> str | None:
    """The embedding model recorded for this collection, or None if unknown.

    None means "no provenance recorded" (empty store, pre-migration corpus, or
    a transient database error) — callers treat it as unverified, never as a
    match.
    """
    try:
        with get_engine().connect() as conn:
            value = conn.execute(
                text(
                    "SELECT cmetadata FROM langchain_pg_collection "
                    "WHERE name = :name"
                ),
                {"name": COLLECTION_NAME},
            ).scalar()
    except Exception:
        logger.warning("Could not read stored embedding model metadata.")
        return None
    if not isinstance(value, dict):
        # psycopg2 returns a parsed dict for jsonb columns; older drivers or a
        # JSON string value fall through to a defensive parse.
        try:
            value = json.loads(value) if isinstance(value, str) else {}
        except (TypeError, ValueError):
            value = {}
    return value.get("embedding_model")


@lru_cache
def get_retriever():
    """Hybrid retriever (vector + full-text, optional rerank) used by /query
    and /query/stream. Imported lazily to avoid an import cycle."""
    from app.retrieval import HybridRetriever

    return HybridRetriever()


def ensure_fts_index() -> None:
    """Idempotently add the full-text ``tsvector`` column + GIN index.

    Runs at startup after ingestion so the table exists. Failures (fresh DB
    without tables, older driver) are logged and non-fatal: full-text search
    simply falls back to vector-only.
    """
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE langchain_pg_embedding "
                    "ADD COLUMN IF NOT EXISTS tsv tsvector "
                    "GENERATED ALWAYS AS (to_tsvector('english', document)) STORED"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_lpe_tsv "
                    "ON langchain_pg_embedding USING GIN (tsv)"
                )
            )
    except Exception:
        logger.warning("Could not ensure full-text index; vector-only retrieval.", exc_info=True)
