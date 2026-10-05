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
from app.db import get_engine, read_corpus_generation, stored_corpus_generation
from app.metrics import inc
from app.quotes import parse_quotes, verify_quotes

logger = logging.getLogger(__name__)

EMBED_DIM = 384
SIMILARITY_THRESHOLD = 0.95
TTL_DAYS = 7
MAX_ENTRIES = 2000
CACHE_CONTRACT_VERSION = "source-status-v2"

# Sentinel distinguishing "caller did not bind a generation" (derive the active
# one now, the legacy behavior) from an explicit ``None`` (the corpus itself is
# uninitialized and must be bound as such).
_UNSET = object()


def capture_generation() -> str | None:
    """Read the active corpus generation once, for request-scoped binding.

    Callers pass the returned value to :func:`lookup`, the retriever, and
    :func:`store` so every cache decision in one request refers to the same
    corpus generation even if a rebuild commits midway through the request.

    Returns ``None`` only when the corpus metadata is genuinely absent (an
    uninitialized corpus). Request paths must then disable both the cache and
    live retrieval and fall back to the labelled demo answer: an unknown
    generation must never be forwarded as ``None`` to the unbound retriever or
    turned into an "uninitialized" cache namespace. A database failure while
    reading the metadata raises :class:`app.db.CorpusMetadataError` so it is
    never silently confused with an uninitialized corpus.
    """
    return read_corpus_generation()

_TABLE_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS query_cache (
        id BIGSERIAL PRIMARY KEY,
        question TEXT NOT NULL,
        language VARCHAR(8) NOT NULL,
        profile_hash VARCHAR(64) NOT NULL,
        namespace VARCHAR(64) NOT NULL,
        embedding vector(384) NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """
)
_NAMESPACE_COLUMN_SQL = text(
    "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS namespace "
    "VARCHAR(64) NOT NULL DEFAULT 'legacy'"
)
_INDEX_SQL = text(
    "CREATE INDEX IF NOT EXISTS query_cache_namespace_profile_idx "
    "ON query_cache (namespace, language, profile_hash)"
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


def _answer_prompt_version() -> str:
    """Answer-prompt version, imported lazily to avoid an ``app.rag`` cycle.

    ``app.rag`` imports this module at import time, so importing it at module
    level here would form a cycle. By call time the answer module is loaded.
    """
    from app.rag import PROMPT_VERSION

    return PROMPT_VERSION


def cache_namespace(generation: Any = _UNSET) -> str:
    """Version cache entries by the exact answer pipeline that produced them.

    A cached answer is only valid for the verifier contract, the embedding
    model, the answer model, the answer-prompt version, and the corpus
    generation it was generated from. A different answer model or prompt
    version can word, quote, or reason differently, so both are part of the
    namespace and invalidate stale entries.

    ``generation`` is an explicit corpus generation captured by the caller. When
    omitted the active generation is read at call time, preserving the previous
    API; new code should capture once and pass the same value to ``lookup`` and
    ``store`` so a concurrent rebuild cannot retarget a store.

    A known generation is mandatory: an unknown generation has no valid cache
    namespace (the old ``"uninitialized"`` fallback could serve a cross-corpus
    answer), so this raises instead of fabricating one.
    """
    if generation is _UNSET:
        generation = stored_corpus_generation()
    if not generation:
        raise ValueError("cache_namespace requires a known corpus generation")
    material = "|".join(
        (
            CACHE_CONTRACT_VERSION,
            settings.embedding_model,
            settings.groq_model,
            _answer_prompt_version(),
            generation,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def revalidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recompute citation flags from cached answer text and current sources."""
    validated = dict(payload)
    quotes = verify_quotes(
        parse_quotes(str(validated.get("answer", ""))),
        list(validated.get("sources") or []),
    )
    validated["quotes"] = [quote.__dict__ for quote in quotes]
    return validated


def _ensure_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(_TABLE_SQL)
        conn.execute(_NAMESPACE_COLUMN_SQL)
        conn.execute(_INDEX_SQL)


def lookup(
    question: str,
    language: str,
    profile_h: str,
    generation: Any = _UNSET,
) -> dict[str, Any] | None:
    """Return the cached payload for a semantically-equal question, or None.

    Similarity is cosine on the question embedding; a hit also requires an
    exact match on language and profile hash and a fresh-enough entry.

    ``generation`` binds the lookup to one corpus generation. The namespace is
    derived from that value, so only entries produced from the same corpus are
    candidates. A hit is accepted only if the active corpus generation still
    equals the bound generation: a rebuild that commits during the lookup turns
    the would-be hit into a miss rather than serving a cross-generation answer.

    An unknown generation disables the cache entirely (a miss): there is no
    namespace that could safely match a corpus-bound answer.
    """
    if not getattr(settings, "enable_semantic_cache", True):
        return None
    try:
        from app.db import get_embeddings

        bound_generation = (
            read_corpus_generation() if generation is _UNSET else generation
        )
        if not bound_generation:
            inc("cache_generation_miss")
            return None
        engine = get_engine()
        _ensure_table(engine)
        vector = get_embeddings().embed_query(question)
        vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
        namespace = cache_namespace(bound_generation)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT payload, 1 - (embedding <=> CAST(:vec AS vector)) AS sim "
                    "FROM query_cache "
                    "WHERE namespace = :namespace "
                    "AND language = :lang AND profile_hash = :phash "
                    "AND created_at > now() - (:ttl || ' days')::interval "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 1"
                ),
                {
                    "vec": vector_literal,
                    "namespace": namespace,
                    "lang": language,
                    "phash": profile_h,
                    "ttl": TTL_DAYS,
                },
            ).first()
        if row is None or float(row[1]) < SIMILARITY_THRESHOLD:
            inc("cache_miss")
            return None
        if stored_corpus_generation() != bound_generation:
            logger.info(
                "Cache hit rejected: active corpus generation changed during lookup."
            )
            inc("cache_generation_miss")
            return None
        inc("cache_hit")
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return payload
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
    generation: Any = _UNSET,
) -> None:
    """Cache a live answer payload (best-effort, never raises).

    ``generation`` is the corpus generation the answer was retrieved from.
    The entry is written under the namespace derived from that same value, and
    only when it is still the active generation. If a rebuild committed between
    retrieval and store, the write is skipped: an answer grounded in one corpus
    is never filed under another, even though a lookup would also refuse it.

    An unknown generation is never stored: there is no namespace under which the
    answer could later be matched safely.
    """
    if not getattr(settings, "enable_semantic_cache", True):
        return
    try:
        from app.db import get_embeddings

        bound_generation = (
            read_corpus_generation() if generation is _UNSET else generation
        )
        if not bound_generation:
            inc("cache_generation_skipped")
            return
        engine = get_engine()
        _ensure_table(engine)
        if stored_corpus_generation() != bound_generation:
            logger.info(
                "Cache store skipped: corpus generation changed after retrieval."
            )
            inc("cache_generation_skipped")
            return
        vector = get_embeddings().embed_query(question)
        vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
        namespace = cache_namespace(bound_generation)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO query_cache "
                    "(question, language, profile_hash, namespace, embedding, payload) "
                    "VALUES (:q, :lang, :phash, :namespace, "
                    "CAST(:vec AS vector), CAST(:payload AS JSONB))"
                ),
                {
                    "q": question[:2000],
                    "lang": language,
                    "phash": profile_h,
                    "namespace": namespace,
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
