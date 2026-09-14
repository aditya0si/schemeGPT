"""Hybrid retrieval: full-text + vector similarity + lexical source matching.

Three evidence channels are combined so retrieval is robust when a query has
strong keyword matches (full-text: ``tsvector`` over the chunk text) *or*
semantic matches (vector: pgvector cosine in the multilingual embedding space)
*or* an explicit scheme name (lexical: source-filename + chunk-content token
overlap). Hinglish and scheme-name queries such as ``pm kisan`` or ``dpiit
startup india`` are exactly where the first two channels are weakest, so the
lexical channel anchors them to canonical ``schemes/*`` documents. The ranked
lists are merged with Reciprocal Rank Fusion (RRF), which needs no tunable
weight between the channels.

Optionally (``settings.enable_reranker``), a CPU cross-encoder re-scores the
fused shortlist. Cross-encoders are slow but far more accurate at judging
query-passage relevance; the default ``BAAI/bge-reranker-base`` model is ~2 GB
in memory, so it stays OFF for small free-tier VPSes and is never loaded at
import time or in tests.
"""

import hashlib
import logging
import re
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import text

from app.config import settings
from app.db import (
    VECTOR_GENERATION_COLUMN,
    VECTOR_METADATA_COLUMN,
    VECTOR_TABLE,
    get_engine,
)

logger = logging.getLogger(__name__)

RERANK_K = 60
VECTOR_TOP_K = 12
FTS_LIMIT = 12
LEXICAL_SOURCE_LIMIT = 8
FINAL_K = 4

# Small English + Hinglish function-word set. Dropping these keeps the lexical
# channel focused on salient scheme-name tokens (kisan, startup, dpiit, ...)
# without a database-backed stopword table or any new dependency.
_QUERY_STOPWORDS = frozenset(
    {
        # English function words
        "what", "does", "is", "the", "for", "and", "how", "much", "who",
        "are", "from", "of", "to", "in", "on", "at", "with", "that", "this",
        "which", "when", "where", "why", "can", "could", "should", "would",
        "about", "into", "than", "then", "there", "under", "any", "all",
        "its", "as", "by", "or", "not", "you", "your",
        # Hinglish function words
        "ka", "ke", "ki", "ko", "hai", "hain", "kitne", "kitni", "kitna",
        "kya", "mera", "meri", "mujhe", "banao", "chune", "har", "saal",
        "deti", "aata", "kab", "kaun", "kis", "kuch", "koi", "bhi", "se",
        "mein", "par", "tha", "nahi",
    }
)


def _doc_id(doc: Document) -> str:
    """Content-hash stable key for deduplicating across retrieval channels."""
    return hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()


def rrf_fuse(
    *channels: list[tuple[Document, float]],
    k: int = RERANK_K,
) -> list[Document]:
    """Merge any number of ranked (doc, score) lists via Reciprocal Rank Fusion.

    RRF score = sum over lists of 1 / (k + rank), where rank is 1-based.
    Only the ORDER within each list matters, not the raw similarity scores, so
    every channel contributes on equal footing regardless of its scale.
    """
    fused: dict[str, list] = {}
    for hits in channels:
        for rank, (doc, _score) in enumerate(hits, start=1):
            key = _doc_id(doc)
            entry = fused.setdefault(key, {"doc": doc, "rrf": 0.0})
            entry["rrf"] += 1.0 / (k + rank)
    ranked = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
    return [entry["doc"] for entry in ranked]


def _select_diverse(docs: list[Document], final_k: int) -> list[Document]:
    """Keep the first chunk per metadata ``source`` so the top-k are distinct docs.

    Near-duplicate myScheme imports can otherwise fill every slot with chunks
    of the same file; capping each source to one entry preserves the fused rank
    order while widening provenance coverage.
    """
    selected: list[Document] = []
    seen: set[object] = set()
    for doc in docs:
        source = doc.metadata.get("source")
        if source is not None:
            if source in seen:
                continue
            seen.add(source)
        selected.append(doc)
        if len(selected) >= final_k:
            break
    return selected


@lru_cache
def _reranker():
    """Lazily load the cross-encoder once; never at import time."""
    from sentence_transformers import CrossEncoder

    logger.info("Loading cross-encoder reranker BAAI/bge-reranker-base ...")
    return CrossEncoder("BAAI/bge-reranker-base")


def _full_text_search(
    query: str, corpus_generation: str | None = None
) -> list[tuple[Document, float]]:
    """Keyword search over the chunk ``tsvector`` (needs no embedding call).

    When ``corpus_generation`` is given the search is restricted to rows from
    that generation, so a concurrent rebuild can never fuse full-text hits from
    one corpus with vector hits from another.
    """
    where = "tsv @@ websearch_to_tsquery('english', :q)"
    params: dict[str, object] = {"q": query, "lim": FTS_LIMIT}
    if corpus_generation is not None:
        where += f" AND {VECTOR_GENERATION_COLUMN} = :generation"
        params["generation"] = corpus_generation
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT content, {VECTOR_METADATA_COLUMN}, "
                    "ts_rank(tsv, websearch_to_tsquery('english', :q)) AS score "
                    f"FROM {VECTOR_TABLE} "
                    f"WHERE {where} "
                    "ORDER BY score DESC LIMIT :lim"
                ),
                params,
            ).fetchall()
    except Exception as exc:
        # FTS is an enhancement: a missing index/column (fresh DB) must not
        # break retrieval entirely; fall back to vector-only via empty results.
        logger.warning("Full-text retrieval unavailable (%s); vector-only.", type(exc).__name__)
        return []
    return [
        (Document(page_content=row[0], metadata=row[1] or {}), float(row[2] or 0.0))
        for row in rows
    ]


def _query_tokens(query: str) -> list[str]:
    """Lowercase alphanumeric tokens of length >= 3, minus function words."""
    raw = re.split(r"[^a-z0-9]+", query.lower())
    return [token for token in raw if len(token) >= 3 and token not in _QUERY_STOPWORDS]


def _slug_tokens(source: str) -> list[str]:
    """Split a source path/slug on hyphen, underscore, slash, and dot."""
    return [token for token in re.split(r"[^a-z0-9]+", source.lower()) if token]


def _phrase_present(tokens: list[str], source: str) -> bool:
    """True when a contiguous multi-token query phrase appears in the slug."""
    lowered = source.lower()
    for size in range(len(tokens), 1, -1):
        for start in range(len(tokens) - size + 1):
            if "-".join(tokens[start : start + size]) in lowered:
                return True
    return False


def _rank_sources(tokens: list[str], sources: tuple[str, ...]) -> list[str]:
    """Rank sources by query-token overlap with the slug, best canonical first.

    A source qualifies only when at least one matched token is >= 4 characters,
    which filters out incidental short-token noise. Ties break on full
    multi-token phrase presence, then on shorter (more canonical) source paths.
    """
    query_set = set(tokens)
    scored: list[tuple[int, int, int, str]] = []
    for source in sources:
        matched = query_set & set(_slug_tokens(source))
        if not matched or not any(len(token) >= 4 for token in matched):
            continue
        phrase = 1 if _phrase_present(tokens, source) else 0
        scored.append((len(matched), phrase, len(source), source))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    return [item[3] for item in scored[:LEXICAL_SOURCE_LIMIT]]


@lru_cache(maxsize=8)
def _generation_sources(corpus_generation: str | None) -> tuple[str, ...]:
    """Distinct metadata ``source`` values for one generation (cached once).

    The DISTINCT scan over ~20k rows is the expensive part of the lexical
    channel, so it is memoized per generation; a corpus rebuild activates a new
    generation id, which naturally invalidates the entry.
    """
    source_expr = f"{VECTOR_METADATA_COLUMN} ->> 'source'"
    where = f"{source_expr} IS NOT NULL"
    params: dict[str, object] = {}
    if corpus_generation is not None:
        where += f" AND {VECTOR_GENERATION_COLUMN} = :generation"
        params["generation"] = corpus_generation
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT {source_expr} FROM {VECTOR_TABLE} WHERE {where}"),
            params,
        ).fetchall()
    return tuple(str(row[0]) for row in rows if row[0])


def _fetch_source_chunks(
    sources: list[str], corpus_generation: str | None
) -> list[tuple]:
    """Chunks for the matched sources, generation-filtered and parameterized."""
    placeholders = ", ".join(f":source_{index}" for index in range(len(sources)))
    params: dict[str, object] = {
        f"source_{index}": source for index, source in enumerate(sources)
    }
    where = f"{VECTOR_METADATA_COLUMN} ->> 'source' IN ({placeholders})"
    if corpus_generation is not None:
        where += f" AND {VECTOR_GENERATION_COLUMN} = :generation"
        params["generation"] = corpus_generation
    with get_engine().connect() as conn:
        return conn.execute(
            text(
                f"SELECT content, {VECTOR_METADATA_COLUMN} "
                f"FROM {VECTOR_TABLE} WHERE {where}"
            ),
            params,
        ).fetchall()


def _chunk_index(metadata: dict) -> int:
    try:
        return int(metadata.get("chunk_index", 0))
    except (TypeError, ValueError):
        return 0


def _content_token_hits(content: str, tokens: list[str]) -> int:
    lowered = content.lower()
    return sum(1 for token in tokens if token in lowered)


def _lexical_search(
    query: str, corpus_generation: str | None = None
) -> list[tuple[Document, float]]:
    """Source-name/chunk-content lexical channel (needs no embedding call).

    Stage 1 expands salient query tokens against the distinct ``source`` slugs
    of the pinned generation, anchoring scheme-name queries to canonical files.
    Stage 2 fetches those sources' chunks and keeps the best-matching chunk per
    source, ordered by content token overlap then ``chunk_index``.

    Like :func:`_full_text_search`, this channel is an enhancement: any failure
    (missing table, permission error, malformed metadata) is logged and
    degraded to an empty list so it can never hard-fail retrieval.
    """
    try:
        tokens = _query_tokens(query)
        if not tokens:
            return []
        sources = _generation_sources(corpus_generation)
        matched_sources = _rank_sources(tokens, sources)
        if not matched_sources:
            return []
        rows = _fetch_source_chunks(matched_sources, corpus_generation)
    except Exception as exc:
        logger.warning(
            "Lexical retrieval unavailable (%s); skipping channel.",
            type(exc).__name__,
        )
        return []

    ranked: list[tuple[int, int, int, Document, int]] = []
    for order, row in enumerate(rows):
        content = row[0]
        metadata = row[1] or {}
        hits = _content_token_hits(content, tokens)
        ranked.append(
            (
                -hits,
                _chunk_index(metadata),
                order,
                Document(page_content=content, metadata=metadata),
                hits,
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))

    results: list[tuple[Document, float]] = []
    seen: set[object] = set()
    for _neg_hits, _index, _order, doc, hits in ranked:
        source = doc.metadata.get("source")
        if source in seen:
            continue
        seen.add(source)
        results.append((doc, float(hits)))
    return results


class HybridRetriever(BaseRetriever):
    """Vector + full-text + lexical retriever with RRF, optional rerank.

    ``corpus_generation`` pins retrieval to one atomically activated corpus
    generation. When set, every channel filters on the generation column, so a
    request can never observe a mixed corpus even if a rebuild commits between
    the queries. When ``None`` the retriever behaves as before (search the
    whole active table).
    """

    vector_top_k: int = VECTOR_TOP_K
    final_k: int = FINAL_K
    corpus_generation: str | None = None

    def _generation_filter(self) -> dict[str, str] | None:
        if self.corpus_generation is None:
            return None
        return {VECTOR_GENERATION_COLUMN: self.corpus_generation}

    def _vector_search(self, query: str) -> list[tuple[Document, float]]:
        from app.db import get_vectorstore

        return get_vectorstore().similarity_search_with_score(
            query, k=self.vector_top_k, filter=self._generation_filter()
        )

    def _rerank(self, query: str, docs: list[Document]) -> list[Document]:
        model = _reranker()
        pairs = [(query, doc.page_content) for doc in docs]
        scores = model.predict(pairs)
        ordered = sorted(
            zip(docs, scores), key=lambda pair: float(pair[1]), reverse=True
        )
        return [doc for doc, _score in ordered]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        vector_hits = self._vector_search(query)
        fts_hits = _full_text_search(query, self.corpus_generation)
        lexical_hits = _lexical_search(query, self.corpus_generation)
        fused = rrf_fuse(vector_hits, fts_hits, lexical_hits)
        if settings.enable_reranker and len(fused) > 1:
            shortlist = self.vector_top_k + FTS_LIMIT + LEXICAL_SOURCE_LIMIT
            fused = self._rerank(query, fused[:shortlist])
        selected = _select_diverse(fused, self.final_k)
        # The generation document prompt requires explicit provenance fields.
        # Older vectors may predate data_status, so label them unknown rather
        # than failing the whole answer chain or inventing a verified status.
        for doc in selected:
            doc.metadata.setdefault("source", "unknown")
            doc.metadata.setdefault("data_status", "unknown")
        return selected
