"""The synchronous RAG path must use the production retrieval pieces."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.schemas import QueryResponse

import app.rag as rag


def test_format_documents_preserves_canonical_provenance():
    docs = [
        Document(
            page_content="Policy text",
            metadata={
                "source": "schemes/example.md",
                "data_status": "sample_verified",
            },
        )
    ]

    assert rag._format_documents(docs) == (
        "Source: schemes/example.md\n"
        "Data status: sample_verified\n"
        "Policy text:\nPolicy text"
    )


def test_get_retriever_uses_the_production_hybrid_retriever():
    with patch.object(rag, "get_hybrid_retriever", return_value="HYBRID") as factory:
        assert rag.get_retriever() == "HYBRID"
    factory.assert_called_once_with()


def test_live_answer_returns_verified_quotes_and_caches_them():
    source = Document(
        page_content="PM-SYM offers a monthly pension to unorganised workers.",
        metadata={
            "source": "schemes/pm-sym.md",
            "data_status": "sample_verified",
        },
    )
    chain = MagicMock()
    chain.invoke.return_value = (
        "> PM-SYM offers a monthly pension to unorganised workers. "
        "[schemes/pm-sym.md, sample_verified]"
    )
    with (
        patch.object(rag.settings, "groq_api_key", "configured"),
        patch.object(rag.semantic_cache, "capture_generation", return_value="gen-1"),
        patch.object(rag.semantic_cache, "lookup", return_value=None) as lookup,
        patch.object(rag.semantic_cache, "store") as store,
        patch.object(
            rag,
            "retrieve_context",
            return_value=([source], [{"tool": "search_schemes", "summary": "1 result"}]),
        ) as retrieve,
        patch.object(rag, "build_answer_chain", return_value=chain),
    ):
        payload = rag.answer("Who receives a PM-SYM pension?")

    lookup.assert_called_once_with(
        "Who receives a PM-SYM pension?", "en", "none", "gen-1"
    )
    retrieve.assert_called_once_with(
        "Who receives a PM-SYM pension?", "en", None, "gen-1"
    )
    invocation = chain.invoke.call_args.args[0]
    assert invocation["context"] == [source]
    assert payload["steps"] == [{"tool": "search_schemes", "summary": "1 result"}]
    assert payload["quotes"][0]["verified"] is True
    assert payload["quotes"][0]["matched_source"] == "schemes/pm-sym.md"
    assert payload["steps"] == [{"tool": "search_schemes", "summary": "1 result"}]
    invoked = chain.invoke.call_args.args[0]
    assert invoked["context"] == [source]
    store.assert_called_once()
    assert store.call_args.args[4] == "gen-1"
    cached_payload = store.call_args.args[3]
    assert cached_payload["quotes"] == payload["quotes"]


def test_cached_sync_answer_revalidates_legacy_quote_flags():
    cached = {
        "answer": "> Fabricated policy. [schemes/a.md, sample_verified]",
        "sources": [
            {
                "source": "schemes/a.md",
                "content": "Real policy.",
                "data_status": "sample_verified",
            }
        ],
        "quotes": [{"verified": True, "matched_source": "schemes/a.md"}],
        "mode": "live",
        "language": "en",
    }
    with (
        patch.object(rag.settings, "groq_api_key", "configured"),
        patch.object(rag.semantic_cache, "capture_generation", return_value="gen-1"),
        patch.object(rag.semantic_cache, "lookup", return_value=cached),
    ):
        payload = rag.answer("cached question")

    assert payload["cached"] is True
    assert payload["quotes"][0]["verified"] is False
    assert payload["quotes"][0]["matched_source"] is None


def test_no_key_bypasses_live_cache_and_returns_demo(monkeypatch):
    lookup = MagicMock(return_value={"mode": "live", "answer": "stale cache"})
    monkeypatch.setattr(rag.settings, "groq_api_key", "")
    monkeypatch.setattr(rag.semantic_cache, "lookup", lookup)

    payload = rag.answer("cached question")

    assert payload["mode"] == "demo"
    lookup.assert_not_called()


def test_retrieve_context_normalizes_then_uses_hybrid_retriever():
    retriever = MagicMock()
    retriever.invoke.return_value = ["DOC"]
    with (
        patch.object(rag, "_needs_multi_step", return_value=False),
        patch.object(rag, "normalize_question", return_value="clean query") as normalize,
        patch.object(rag, "get_retriever", return_value=retriever) as get,
    ):
        docs, steps = rag.retrieve_context("raw query", "en", None, "gen-1")
    normalize.assert_called_once_with("raw query")
    get.assert_called_once_with("gen-1")
    retriever.invoke.assert_called_once_with("clean query")
    assert docs == ["DOC"]
    assert steps == []


def test_retrieve_context_refuses_unbound_retrieval():
    retrieve = MagicMock()
    with (
        patch.object(rag, "_needs_multi_step", return_value=False),
        patch.object(rag, "get_retriever", return_value=retrieve),
    ):
        with pytest.raises(RuntimeError, match="corpus generation"):
            rag.retrieve_context("raw query", "en", None, None)
    retrieve.invoke.assert_not_called()


def test_retrieve_context_uses_agent_for_complex_questions():
    with (
        patch.object(rag, "_needs_multi_step", return_value=True),
        patch.object(rag, "_run_agent_gather", return_value=(["A", "B"], [{"tool": "search"}])) as gather,
    ):
        docs, steps = rag.retrieve_context("compare a and b", "en", None, "gen-1")
    gather.assert_called_once_with("compare a and b", "en", None, "gen-1")
    assert docs == ["A", "B"]
    assert steps == [{"tool": "search"}]


def test_query_response_preserves_structured_quote_verification():
    response = QueryResponse(
        answer="grounded",
        sources=[],
        quotes=[
            {
                "text": "grounded",
                "source": "schemes/example.md",
                "status": "sample_verified",
                "verified": True,
                "matched_source": "schemes/example.md",
            }
        ],
        steps=[{"tool": "search_schemes", "summary": "1 result"}],
    )
    dumped = response.model_dump()
    assert dumped["quotes"][0]["verified"] is True
    assert dumped["steps"][0]["tool"] == "search_schemes"


def test_normalize_language_values():
    assert rag._normalize_language("hi") == "hi"
    assert rag._normalize_language("HI") == "hi"
    assert rag._normalize_language("en") == "en"
    assert rag._normalize_language(None) == "en"
    assert rag._normalize_language("xx") == "en"
