"""Agentic router heuristic + generation-bound tool-calling loop.

The LLM is mocked and every answer-producing tool is bound to a known corpus
generation; the generation-pinned database reads are mocked, so no DB, network,
or live filesystem access happens here.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app import agent


# --- needs_multi_step heuristic truth table --------------------------------

def test_router_routes_comparative_questions():
    assert agent.needs_multi_step("PM-KISAN or PM-SYM, which is better for me?")
    assert agent.needs_multi_step("compare PM-KISAN and PM-SYM")


def test_router_routes_two_scheme_mentions():
    assert agent.needs_multi_step("difference between PM-KISAN and PM-SYM")


def test_router_routes_profile_aware_question_with_profile():
    assert agent.needs_multi_step("give me a pension scheme", profile={"age": 40})
    # Hinglish self-reference only routes to the agent when a profile is attached.
    assert not agent.needs_multi_step("mera pension kaun sa scheme")
    assert agent.needs_multi_step("mera pension kaun sa scheme", profile={"age": 40})


def test_router_keeps_simple_questions_single_shot():
    assert not agent.needs_multi_step("How much does PM-KISAN pay per year?")
    assert not agent.needs_multi_step("What pension does PM-SYM provide at 60?")
    assert not agent.needs_multi_step("pm kisan ka paisa")


# --- tool-calling loop -----------------------------------------------------


def _fake_model(*responses):
    responses = list(responses)

    class Model:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return responses.pop(0)

    return Model()


def _resp(tool_calls=None, content=""):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tc(call_id, name, args):
    return {"id": call_id, "name": name, "args": args}


def _doc(text, source="schemes/x.md"):
    return Document(page_content=text, metadata={"source": source})


def test_agent_loop_gathers_docs_and_steps():
    model = _fake_model(
        _resp(tool_calls=[_tc("c1", "search_schemes", {"query": "pension"})]),
        _resp(),  # final answer
    )
    with (
        patch("app.agent.get_llm", return_value=model),
        patch("app.agent.search_schemes", return_value=[_doc("pension a"), _doc("pension b")]) as search,
        patch("app.agent.list_jurisdictions", return_value=[_doc("states")]),
    ):
        docs, steps = agent.run_agent_gather(
            "compare pension schemes", corpus_generation="gen-1"
        )

    assert len(steps) == 1
    assert steps[0]["tool"] == "search_schemes"
    assert {d.page_content for d in docs} == {"pension a", "pension b"}
    # The loop threads the captured generation into every tool call.
    assert search.call_args.args[2] == "gen-1"


def test_agent_loop_caps_at_max_steps():
    # Six tool-only responses: the loop must run at most MAX_STEPS times.
    model = _fake_model(*[
        _resp(tool_calls=[_tc(f"c{j}", "search_schemes", {"query": "q"})])
        for j in range(6)
    ])
    with (
        patch("app.agent.get_llm", return_value=model),
        patch("app.agent.search_schemes", return_value=[_doc("doc capped")]),
    ):
        docs, steps = agent.run_agent_gather("question", corpus_generation="gen-1")
    assert len(steps) == agent.MAX_STEPS
    assert docs  # gathered context is still returned


def test_agent_loop_dedupes_repeated_docs():
    model = _fake_model(
        _resp(tool_calls=[_tc("c1", "search_schemes", {"query": "a"})]),
        _resp(tool_calls=[_tc("c2", "search_schemes", {"query": "b"})]),
        _resp(),
    )
    with (
        patch("app.agent.get_llm", return_value=model),
        patch("app.agent.search_schemes", return_value=[_doc("same text two")]),
    ):
        docs, _ = agent.run_agent_gather("question", corpus_generation="gen-1")
    assert len(docs) == 1  # identical content deduped by (source, text[:80])


def test_agent_loop_raises_when_no_context_gathered():
    model = _fake_model(_resp())  # answers directly, no tools
    with patch("app.agent.get_llm", return_value=model):
        with pytest.raises(RuntimeError):
            agent.run_agent_gather("answer me directly", corpus_generation="gen-1")


def test_agent_loop_refuses_unknown_generation():
    # No generation: every tool would be unbound, so the loop must not start.
    with patch("app.agent.get_llm", return_value=_fake_model(_resp())):
        with pytest.raises(ValueError, match="corpus generation"):
            agent.run_agent_gather("compare pension schemes", corpus_generation=None)


# --- tools bound to a known generation -------------------------------------


def test_search_schemes_binds_retriever_to_generation():
    retriever = MagicMock()
    retriever.invoke.return_value = [_doc("pension")]
    with patch("app.retrieval.HybridRetriever", return_value=retriever) as factory:
        docs = agent.search_schemes("pension", corpus_generation="gen-7")

    factory.assert_called_once_with(corpus_generation="gen-7")
    retriever.invoke.assert_called_once_with("pension")
    assert docs == retriever.invoke.return_value


def test_search_schemes_requires_generation():
    with pytest.raises(ValueError, match="corpus generation"):
        agent.search_schemes("pension")


def test_get_scheme_details_reads_pinned_db_generation():
    records = [
        {
            "content": "PM-KISAN gives ₹6,000 per year.",
            "metadata": {
                "source": "schemes/pm-kisan.md",
                "data_status": "sample_verified",
            },
        }
    ]
    with patch(
        "app.agent.fetch_generation_documents", return_value=records
    ) as fetch:
        docs = agent.get_scheme_details("pm-kisan.md", corpus_generation="gen-9")

    fetch.assert_called_once_with("gen-9", source="pm-kisan.md")
    assert len(docs) == 1
    assert "PM-KISAN" in docs[0].page_content
    assert docs[0].metadata["data_status"] == "sample_verified"
    assert docs[0].metadata["corpus_generation"] == "gen-9"


def test_get_scheme_details_missing_id_is_labelled_not_filesystem():
    with patch("app.agent.fetch_generation_documents", return_value=[]) as fetch:
        docs = agent.get_scheme_details("does-not-exist.md", corpus_generation="gen-9")

    fetch.assert_called_once_with("gen-9", source="does-not-exist.md")
    assert "No scheme found" in docs[0].page_content
    assert docs[0].metadata["corpus_generation"] == "gen-9"


def test_get_scheme_details_requires_generation():
    with pytest.raises(ValueError, match="corpus generation"):
        agent.get_scheme_details("pm-kisan.md")


def test_list_jurisdictions_reads_pinned_db_generation():
    with patch(
        "app.agent.fetch_generation_jurisdictions",
        return_value=["Bihar", "Kerala"],
    ) as fetch:
        docs = agent.list_jurisdictions(corpus_generation="gen-3")

    fetch.assert_called_once_with("gen-3")
    assert "Covered jurisdictions" in docs[0].page_content
    assert "Bihar" in docs[0].page_content
    assert docs[0].metadata["corpus_generation"] == "gen-3"


def test_list_jurisdictions_requires_generation():
    with pytest.raises(ValueError, match="corpus generation"):
        agent.list_jurisdictions()


def test_tool_map_threads_one_generation_into_every_tool():
    with (
        patch("app.agent.search_schemes", return_value=[_doc("s")]) as search,
        patch("app.agent.get_scheme_details", return_value=[_doc("d")]) as details,
        patch("app.agent.list_jurisdictions", return_value=[_doc("j")]) as jurisdictions,
    ):
        tool_map = agent._tool_map("gen-42")
        tool_map["search_schemes"]("q")
        tool_map["get_scheme_details"]("pm-kisan.md")
        tool_map["list_jurisdictions"]()

    assert search.call_args.args == ("q", None, "gen-42")
    assert details.call_args.args == ("pm-kisan.md", "gen-42")
    assert jurisdictions.call_args.args == ("gen-42",)
