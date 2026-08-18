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
from app.db import COLLECTION_NAME, get_engine

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


def _full_text_search(query: str) -> list[tuple[Document, float]]:
    """Keyword search over the chunk ``tsvector`` (needs no embedding call)."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT e.document, e.cmetadata, "
                    "ts_rank(e.tsv, websearch_to_tsquery('english', :q)) AS score "
                    "FROM langchain_pg_embedding e "
                    "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                    "WHERE c.name = :name "
                    "AND e.tsv @@ websearch_to_tsquery('english', :q) "
                    "ORDER BY score DESC LIMIT :lim"
                ),
                {
                    "q": query,
                    "name": COLLECTION_NAME,
                    "lim": FTS_LIMIT,
                },
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
    """Vector + full-text retriever with Reciprocal Rank Fusion, optional rerank."""

    vector_top_k: int = VECTOR_TOP_K
    final_k: int = FINAL_K

    def _vector_search(self, query: str) -> list[tuple[Document, float]]:
        from app.db import get_vectorstore

        return get_vectorstore().similarity_search_with_score(
            query, k=self.vector_top_k
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
        fts_hits = _full_text_search(query)
        fused = rrf_fuse(vector_hits, fts_hits)
        if settings.enable_reranker and len(fused) > 1:
            fused = self._rerank(query, fused[: (self.vector_top_k + FTS_LIMIT)])
        return fused[: self.final_k]
