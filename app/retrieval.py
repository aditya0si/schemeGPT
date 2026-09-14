"""Hybrid retrieval: Postgres full-text fused with vector similarity.

Two evidence channels are combined so retrieval is robust when a query has
strong keyword matches (full-text: ``tsvector`` over the chunk text) *or*
semantic matches (vector: pgvector cosine in the multilingual embedding
space). The two ranked lists are merged with Reciprocal Rank Fusion (RRF),
which needs no tunable weight between the channels.

Optionally (``settings.enable_reranker``), a CPU cross-encoder re-scores the
fused shortlist. Cross-encoders are slow but far more accurate at judging
query-passage relevance; the default ``BAAI/bge-reranker-base`` model is ~2 GB
in memory, so it stays OFF for small free-tier VPSes and is never loaded at
import time or in tests.
"""

import hashlib
import logging
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
VECTOR_TOP_K = 6
FTS_LIMIT = 8
FINAL_K = 4


def _doc_id(doc: Document) -> str:
    """Content-hash stable key for deduplicating across retrieval channels."""
    return hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()


def rrf_fuse(
    vector_hits: list[tuple[Document, float]],
    fts_hits: list[tuple[Document, float]],
    k: int = RERANK_K,
) -> list[Document]:
    """Merge two ranked (doc, score) lists via Reciprocal Rank Fusion.

    RRF score = sum over lists of 1 / (k + rank), where rank is 1-based.
    Only the ORDER within each list matters, not the raw similarity scores, so
    the vector and FTS channels contribute on equal footing.
    """
    fused: dict[str, list] = {}
    for hits in (vector_hits, fts_hits):
        for rank, (doc, _score) in enumerate(hits, start=1):
            key = _doc_id(doc)
            entry = fused.setdefault(key, {"doc": doc, "rrf": 0.0})
            entry["rrf"] += 1.0 / (k + rank)
    ranked = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
    return [entry["doc"] for entry in ranked]


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


class HybridRetriever(BaseRetriever):
    """Vector + full-text retriever with Reciprocal Rank Fusion, optional rerank.

    ``corpus_generation`` pins retrieval to one atomically activated corpus
    generation. When set, both the vector and full-text channels filter on the
    generation column, so a request can never observe a mixed corpus even if a
    rebuild commits between the two queries. When ``None`` the retriever behaves
    as before (search the whole active table).
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
        fused = rrf_fuse(vector_hits, fts_hits)
        if settings.enable_reranker and len(fused) > 1:
            fused = self._rerank(query, fused[: (self.vector_top_k + FTS_LIMIT)])
        selected = fused[: self.final_k]
        # The generation document prompt requires explicit provenance fields.
        # Older vectors may predate data_status, so label them unknown rather
        # than failing the whole answer chain or inventing a verified status.
        for doc in selected:
            doc.metadata.setdefault("source", "unknown")
            doc.metadata.setdefault("data_status", "unknown")
        return selected
