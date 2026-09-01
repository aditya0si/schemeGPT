"""Semantic query cache backed by pgvector.

Answers are keyed by the embedding of the question (not the raw text), so a
paraphrase like "PM-KISAN kitne paise deta hai?" can hit a cache entry stored
under "How much money does PM-KISAN give?". Matches additionally require the
same answer language and the same profile hash: a profile-tailored answer is
never served to a differently-profiled request, and an English answer is never
served to a Hindi request.

Conservative defaults: cosine similarity must be >= 0.95 for a hit, entries
expire after 7 days, and the table is capped so a public deployment cannot
grow it unbounded. Every lookup records cache_hit/cache_miss in app.metrics,
so the hit rate is visible on GET /metrics.

Only live answers are cached; demo fallbacks are never stored. All cache
failures are swallowed (the pipeline continues as a miss) — the cache is an
optimization, never a correctness dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.db import get_engine
from app.metrics import inc

logger = logging.getLogger(__name__)

EMBED_DIM = 384
SIMILARITY_THRESHOLD = 0.95
TTL_DAYS = 7
MAX_ENTRIES = 2000

_TABLE_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS query_cache (
        id BIGSERIAL PRIMARY KEY,
        question TEXT NOT NULL,
        language VARCHAR(8) NOT NULL,
        profile_hash VARCHAR(64) NOT NULL,
        embedding vector(384) NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """
)
_INDEX_SQL = text(
    "CREATE INDEX IF NOT EXISTS query_cache_profile_idx "
    "ON query_cache (language, profile_hash)"
)


def profile_hash(profile: Any) -> str:
    """Stable short hash of a profile payload (or 'none' when absent)."""
    if not profile:
        return "none"
    try:
        canonical = json.dumps(profile, sort_keys=True, default=str)
    except TypeError:
        canonical = str(profile)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _ensure_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(_TABLE_SQL)
        conn.execute(_INDEX_SQL)


def lookup(
    question: str, language: str, profile_h: str
) -> dict[str, Any] | None:
    """Return the cached payload for a semantically-equal question, or None.

    Similarity is cosine on the question embedding; a hit also requires an
    exact match on language and profile hash and a fresh-enough entry.
    """
    if not getattr(settings, "enable_semantic_cache", True):
        return None
    try:
        from app.db import get_embeddings

        engine = get_engine()
        _ensure_table(engine)
        vector = get_embeddings().embed_query(question)
        vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT payload, 1 - (embedding <=> CAST(:vec AS vector)) AS sim "
                    "FROM query_cache "
                    "WHERE language = :lang AND profile_hash = :phash "
                    "AND created_at > now() - (:ttl || ' days')::interval "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 1"
                ),
                {"vec": vector_literal, "lang": language, "phash": profile_h, "ttl": TTL_DAYS},
            ).first()
        if row is None or float(row[1]) < SIMILARITY_THRESHOLD:
            inc("cache_miss")
            return None
        inc("cache_hit")
        payload = row[0]
        return json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        # Cache lookup must never break the query path.
        logger.warning("Cache lookup failed; treating as miss.", exc_info=True)
        inc("cache_error")
        return None


def store(
    question: str,
    language: str,
    profile_h: str,
    payload: dict[str, Any],
) -> None:
    """Cache a live answer payload (best-effort, never raises)."""
    if not getattr(settings, "enable_semantic_cache", True):
        return
    try:
        from app.db import get_embeddings

        engine = get_engine()
        _ensure_table(engine)
        vector = get_embeddings().embed_query(question)
        vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO query_cache "
                    "(question, language, profile_hash, embedding, payload) "
                    "VALUES (:q, :lang, :phash, CAST(:vec AS vector), CAST(:payload AS JSONB))"
                ),
                {
                    "q": question[:2000],
                    "lang": language,
                    "phash": profile_h,
                    "vec": vector_literal,
                    "payload": json.dumps(payload, ensure_ascii=False, default=str),
                },
            )
            conn.execute(
                text(
                    "DELETE FROM query_cache WHERE id IN ("
                    "  SELECT id FROM query_cache ORDER BY created_at DESC "
                    "  OFFSET :cap"
                    ")"
                ),
                {"cap": MAX_ENTRIES},
            )
    except Exception:
        logger.warning("Cache store failed; continuing without caching.", exc_info=True)
        inc("cache_error")
