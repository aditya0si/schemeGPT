"""Agentic router heuristic + tool-calling loop (mocked LLM, no DB/network)."""

from types import SimpleNamespace
from unittest.mock import patch

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
        patch("app.agent.search_schemes", return_value=[_doc("pension a"), _doc("pension b")]),
        patch("app.agent.list_jurisdictions", return_value=[_doc("states")]),
    ):
        docs, steps = agent.run_agent_gather("compare pension schemes")

    assert len(steps) == 1
    assert steps[0]["tool"] == "search_schemes"
    assert {d.page_content for d in docs} == {"pension a", "pension b"}


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
        docs, steps = agent.run_agent_gather("question")
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
        docs, _ = agent.run_agent_gather("question")
    assert len(docs) == 1  # identical content deduped by (source, text[:80])


def test_agent_loop_raises_when_no_context_gathered():
    model = _fake_model(_resp())  # answers directly, no tools
    with patch("app.agent.get_llm", return_value=model):
        try:
            agent.run_agent_gather("answer me directly")
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass


# --- tools against real local data ----------------------------------------


def test_get_scheme_details_real_file():
    docs = agent.get_scheme_details("pm-kisan.md")
    assert len(docs) == 1
    assert "PM-KISAN" in docs[0].page_content
    assert docs[0].metadata.get("data_status") == "sample_verified"


def test_get_scheme_details_unknown_id():
    docs = agent.get_scheme_details("does-not-exist.md")
    assert "No scheme found" in docs[0].page_content


def test_list_jurisdictions_covers_many():
    docs = agent.list_jurisdictions()
    assert "Covered jurisdictions" in docs[0].page_content
    assert len(docs[0].page_content) > 40
