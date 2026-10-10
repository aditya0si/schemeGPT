"""Reciprocal rank fusion maths + hybrid retriever with mocked stores."""
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from app.retrieval import (
    HybridRetriever,
    _logical_document_key,
    _select_diverse,
    rrf_fuse,
)


def _doc(text: str) -> Document:
    # Distinct source per distinct content so the new source-diversity
    # selection is exercised meaningfully by the hybrid tests.
    return Document(page_content=text, metadata={"source": f"schemes/{text}.md"})


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


def test_rrf_fuses_three_channels_and_boosts_consensus():
    a, b, c, d = _doc("a"), _doc("b"), _doc("c"), _doc("d")
    ranked = rrf_fuse(
        [(a, 1.0), (b, 0.9)],
        [(a, 1.0), (c, 0.9)],
        [(a, 1.0), (d, 0.9)],
    )
    # ``a`` is ranked first by every channel, so fusion must put it on top.
    assert ranked[0] is a
    assert len(ranked) == 4


def test_final_selection_dedupes_sources_but_preserves_order():
    first_a = Document(page_content="a-one", metadata={"source": "schemes/a.md"})
    second_a = Document(page_content="a-two", metadata={"source": "schemes/a.md"})
    b = Document(page_content="b-one", metadata={"source": "schemes/b.md"})
    c = Document(page_content="c-one", metadata={"source": "schemes/c.md"})
    selected = _select_diverse([first_a, second_a, b, c], final_k=3)
    assert [doc.page_content for doc in selected] == ["a-one", "b-one", "c-one"]


def test_final_selection_keeps_unlabelled_docs_distinct():
    first = Document(page_content="one", metadata={})
    second = Document(page_content="two", metadata={})
    selected = _select_diverse([first, second], final_k=2)
    assert [doc.page_content for doc in selected] == ["one", "two"]


def _doc_with(source, text, status=None):
    metadata = {"source": source}
    if status is not None:
        metadata["data_status"] = status
    return Document(page_content=text, metadata=metadata)


def test_logical_document_key_groups_copies_and_strips_duplicate_suffix():
    assert _logical_document_key("schemes/pm-kisan.md") == "pm-kisan"
    assert _logical_document_key("myscheme/pm-kisan.md") == "pm-kisan"
    assert _logical_document_key("myscheme/disabled-pension(1).md") == "disabled-pension"
    assert _logical_document_key("myscheme/disabled-pension.md") == "disabled-pension"
    assert _logical_document_key("schemes/pm-sym.md") == "pm-sym"
    # Documented edge: different directories, same basename, intentionally one
    # logical group (the trust rule picks which copy survives).
    assert _logical_document_key("states/sikkim.md") == _logical_document_key(
        "myscheme/sikkim.md"
    )
    # Documented edge: a legitimate trailing numeric parenthetical is stripped.
    assert _logical_document_key("reports/report(2024).md") == "report"
    # Missing/empty source never groups.
    assert _logical_document_key(None) is None
    assert _logical_document_key("") is None


def test_final_selection_prefers_verified_copy_of_same_logical_document():
    auto = _doc_with("myscheme/pm-kisan.md", "auto", "myscheme_import")
    verified = _doc_with("schemes/pm-kisan.md", "verified", "sample_verified")
    other = _doc_with("schemes/pm-sym.md", "other", "sample_verified")
    selected = _select_diverse([auto, verified, other], final_k=4)
    assert [doc.page_content for doc in selected] == ["verified", "other"]


def test_final_selection_places_group_at_best_ranked_member_position():
    # The auto-import is the best-ranked member, so the logical group owns its
    # slot -- but the higher-trust verified copy is what is emitted.
    auto_high = _doc_with("myscheme/pm-kisan.md", "auto", "myscheme_import")
    other = _doc_with("schemes/gst.md", "gst", "sample_verified")
    verified_low = _doc_with("schemes/pm-kisan.md", "verified", "sample_verified")
    selected = _select_diverse([auto_high, other, verified_low], final_k=4)
    assert [doc.page_content for doc in selected] == ["verified", "gst"]


def test_final_selection_follows_documented_trust_precedence():
    unknown = _doc_with("x/a.md", "unknown")
    seed = _doc_with("states/a.md", "seed", "directory_seed")
    auto = _doc_with("myscheme/a.md", "auto", "myscheme_import")
    verified = _doc_with("schemes/a.md", "verified", "sample_verified")
    assert [d.page_content for d in _select_diverse([unknown, seed, auto, verified], 4)] == [
        "verified"
    ]
    assert [d.page_content for d in _select_diverse([unknown, seed, auto], 4)] == ["auto"]
    assert [d.page_content for d in _select_diverse([unknown, seed], 4)] == ["seed"]
    assert [d.page_content for d in _select_diverse([unknown], 4)] == ["unknown"]


def test_final_selection_breaks_trust_ties_on_fused_rank():
    first = _doc_with("myscheme/x.md", "first", "myscheme_import")
    second = _doc_with("myscheme/x(1).md", "second", "myscheme_import")
    assert [d.page_content for d in _select_diverse([first, second], 4)] == ["first"]
    assert [d.page_content for d in _select_diverse([second, first], 4)] == ["second"]


def test_final_selection_is_independent_of_duplicate_row_order():
    """Shuffling the two copies of one document must not change the output."""
    auto = _doc_with("myscheme/pm-kisan.md", "auto", "myscheme_import")
    verified = _doc_with("schemes/pm-kisan.md", "verified", "sample_verified")
    first = _select_diverse([auto, verified], final_k=4)
    second = _select_diverse([verified, auto], final_k=4)
    assert first == second
    assert [d.page_content for d in first] == ["verified"]


def test_final_selection_ignores_which_copy_arrives_first():
    auto = _doc_with("myscheme/pm-kisan.md", "auto", "myscheme_import")
    verified = _doc_with("schemes/pm-kisan.md", "verified", "sample_verified")
    b = _doc_with("schemes/b.md", "b", "sample_verified")
    c = _doc_with("schemes/c.md", "c", "sample_verified")
    one = _select_diverse([auto, verified, b, c], final_k=4)
    two = _select_diverse([verified, auto, b, c], final_k=4)
    assert [d.page_content for d in one] == ["verified", "b", "c"]
    assert one == two


def test_verified_copy_preferred_regardless_of_fetched_row_order(monkeypatch):
    """End-to-end: the lexical channel's row-order fix feeds the trust-aware
    selection, so the verified copy wins however Postgres returns the rows."""
    import app.retrieval as retrieval

    sources = ("myscheme/pm-kisan.md", "schemes/pm-kisan.md")
    rows = [
        (
            "pm kisan kisan benefit from the auto import",
            {
                "source": "myscheme/pm-kisan.md",
                "chunk_index": 0,
                "data_status": "myscheme_import",
            },
        ),
        (
            "pm kisan kisan benefit from the verified source",
            {
                "source": "schemes/pm-kisan.md",
                "chunk_index": 0,
                "data_status": "sample_verified",
            },
        ),
    ]
    monkeypatch.setattr(
        retrieval, "_generation_sources", lambda generation: sources
    )

    calls: list[int] = []

    def fake_fetch(matched_sources, corpus_generation):
        calls.append(1)
        return rows if len(calls) % 2 else list(reversed(rows))

    monkeypatch.setattr(retrieval, "_fetch_source_chunks", fake_fetch)

    def selected_sources() -> list[str]:
        fused = rrf_fuse(retrieval._lexical_search("pm kisan"))
        return [doc.metadata["source"] for doc in _select_diverse(fused, 4)]

    first = selected_sources()
    second = selected_sources()
    assert first == second == ["schemes/pm-kisan.md"]


def _fake_vectorstore(hits, seen=None):
    class FakeStore:
        def similarity_search_with_score(self, query, k, filter=None):
            if seen is not None:
                seen.append(filter)
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
    assert all(d.metadata["data_status"] == "unknown" for d in docs)


def test_hybrid_retriever_filters_both_channels_to_bound_generation():
    d1 = _doc("one")
    seen_filters = []
    fake_engine = _fake_engine([(d1.page_content, {"source": "s"}, 1.0)])
    with (
        patch("app.db.get_vectorstore",
              return_value=_fake_vectorstore([(d1, 0.9)], seen_filters)),
        patch("app.retrieval.get_engine", return_value=fake_engine),
        patch("app.retrieval.settings") as fake_settings,
    ):
        fake_settings.enable_reranker = False
        docs = HybridRetriever(corpus_generation="gen-a").invoke("q")

    assert seen_filters == [{"corpus_generation": "gen-a"}]
    assert fake_engine.conn.fetched["generation"] == "gen-a"
    assert docs


def test_hybrid_retriever_without_generation_stays_unfiltered():
    d1 = _doc("one")
    seen_filters = []
    fake_engine = _fake_engine([(d1.page_content, {"source": "s"}, 1.0)])
    with (
        patch("app.db.get_vectorstore",
              return_value=_fake_vectorstore([(d1, 0.9)], seen_filters)),
        patch("app.retrieval.get_engine", return_value=fake_engine),
        patch("app.retrieval.settings") as fake_settings,
    ):
        fake_settings.enable_reranker = False
        HybridRetriever().invoke("q")

    assert seen_filters == [None]
    assert "generation" not in fake_engine.conn.fetched


def test_lexical_search_is_independent_of_fetched_row_order(monkeypatch):
    """A tied lexical ranking must not depend on unspecified Postgres row order.

    Two near-identical PM-KISAN copies tie on token overlap and ``chunk_index``.
    Serving the same rows in reverse must not change which one ranks first.
    """
    import app.retrieval as retrieval

    sources = ("myscheme/pm-kisan.md", "schemes/pm-kisan.md")
    rows = [
        ("pm kisan kisan benefit", {"source": "schemes/pm-kisan.md", "chunk_index": 0}),
        ("pm kisan kisan benefit", {"source": "myscheme/pm-kisan.md", "chunk_index": 0}),
        ("pm kisan benefit", {"source": "schemes/pm-kisan.md", "chunk_index": 1}),
    ]
    monkeypatch.setattr(retrieval, "_generation_sources", lambda generation: sources)

    calls: list[int] = []

    def fake_fetch(matched_sources, corpus_generation):
        calls.append(1)
        return rows if len(calls) % 2 else list(reversed(rows))

    monkeypatch.setattr(retrieval, "_fetch_source_chunks", fake_fetch)

    first = [doc.metadata["source"] for doc, _ in retrieval._lexical_search("pm kisan")]
    second = [doc.metadata["source"] for doc, _ in retrieval._lexical_search("pm kisan")]

    assert first == second
    assert first == ["myscheme/pm-kisan.md", "schemes/pm-kisan.md"]


def test_generation_sources_returns_a_deterministic_order(monkeypatch):
    """``_generation_sources`` must not leak the DISTINCT scan's row order."""
    import app.retrieval as retrieval

    rows = [("schemes/z.md",), ("schemes/a.md",)]
    monkeypatch.setattr(retrieval, "get_engine", lambda: _fake_engine(rows))
    retrieval._generation_sources.cache_clear()
    try:
        assert retrieval._generation_sources("gen") == ("schemes/a.md", "schemes/z.md")
    finally:
        retrieval._generation_sources.cache_clear()

