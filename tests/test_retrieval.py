"""Reciprocal rank fusion maths + hybrid retriever with mocked stores."""
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from app.retrieval import HybridRetriever, rrf_fuse


def _doc(text: str) -> Document:
    return Document(page_content=text, metadata={"source": "schemes/x.md"})


def test_rrf_prefers_doc_ranked_high_in_both_lists():
    a, b, c = _doc("a"), _doc("b"), _doc("c")
    vector_hits = [(a, 0.9), (b, 0.8), (c, 0.7)]  # a ranked 1, b 2, c 3
    fts_hits = [(b, 9.0), (c, 8.0), (a, 7.0)]    # b ranked 1, c 2, a 3
    # RRF (k=60): a=1/61+1/63, b=1/62+1/61, c=1/63+1/62 -> b > a > c
    ranked = rrf_fuse(vector_hits, fts_hits)
    assert ranked[0] is b
    assert ranked[1] is a
    assert ranked[2] is c


def test_rrf_disambiguates_ties_by_rank():
    a, b = _doc("a"), _doc("b")
    # a: rank 1 + rank 4 ; b: rank 2 + rank 2 -> RRF a = 1/61+1/64,
    # b = 1/62+1/62, which is larger, so b wins despite a being #1 in one list.
    ranked = rrf_fuse([(a, 1.0), (b, 0.9)], [(b, 9.0), (_doc("x"), 8.0),
                                             (_doc("y"), 7.0), (a, 6.0)])
    assert ranked[0] is b
    assert ranked[1] is a


def test_rrf_dedupes_identical_docs_across_channels():
    doc_a = _doc("same content")
    doc_b = _doc("same content")  # identical text -> same content hash
    ranked = rrf_fuse([(doc_a, 0.9)], [(doc_b, 8.0)])
    assert len(ranked) == 1


def _fake_vectorstore(hits):
    class FakeStore:
        def similarity_search_with_score(self, query, k):
            return hits[:k]

    return FakeStore()


def _fake_engine(rows):
    class FakeConn:
        def __init__(self):
            self.fetched = None

        def execute(self, stmt, params):
            self.fetched = params
            return SimpleNamespace(fetchall=lambda: rows)

    class FakeEngine:
        def __init__(self):
            self.conn = FakeConn()

        def connect(self):
            return _Ctx(self.conn)

    class _Ctx:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *a):
            return False

    return FakeEngine()


def test_hybrid_retriever_returns_fused_top_k():
    d1, d2, d3 = _doc("one"), _doc("two"), _doc("three")
    vec = [(d1, 0.9), (d2, 0.8), (d3, 0.7)]
    fts_rows = [
        (d2.page_content, {"source": "s"}, 9.0),
        (d1.page_content, {"source": "s"}, 8.0),
    ]
    with (
        patch("app.db.get_vectorstore",
              return_value=_fake_vectorstore(vec)),
        patch("app.retrieval.get_engine", return_value=_fake_engine(fts_rows)),
        patch("app.retrieval.settings") as fake_settings,
    ):
        fake_settings.enable_reranker = False
        retriever = HybridRetriever()
        docs = retriever.invoke("some query")
    # Both channels contribute; all three sources are fused (final_k=4 covers
    # the 3 unique docs; d3 is present via vector search alone).
    assert len(docs) == 3
    assert {d.page_content for d in docs} == {"one", "two", "three"}
