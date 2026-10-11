"""Conformance: every SchemeGPT implementation satisfies its spine seam.

The seams are structural protocols, so conformance is an ``isinstance`` check.
The second half builds a ``Spine`` from callables that have nothing to do with
SchemeGPT, which is the point of the contract: a client attaches by supplying
these six callables, not by importing SchemeGPT's internals.
"""

from __future__ import annotations

from app import rag, stream
from app.core.scheme import build_scheme_spine, spine
from app.core.seams import (
    Answerer,
    Egress,
    ModelRouter,
    PolicyGate,
    Spine,
    StreamEgress,
    Validator,
)
from app.guardrails.middleware import answer_with_pii_protection
from app.ops import ops
from app.quotes import parse_quotes, validate_quotes, verify_quotes


def test_scheme_implementations_satisfy_their_seams():
    assert isinstance(ops.gate, PolicyGate)
    assert isinstance(rag.get_llm, ModelRouter)
    assert isinstance(rag.answer, Answerer)
    assert isinstance(validate_quotes, Validator)
    assert isinstance(answer_with_pii_protection, Egress)
    assert isinstance(stream.stream_answer, StreamEgress)


def test_scheme_spine_binds_the_existing_modules():
    built = build_scheme_spine()
    assert isinstance(built, Spine)
    assert built.gate == ops.gate
    assert built.router is rag.get_llm
    assert built.answerer is rag.answer
    assert built.validator is validate_quotes
    assert built.egress is answer_with_pii_protection
    assert built.stream is stream.stream_answer
    assert spine == built


def test_validate_seam_is_the_parse_then_verify_composition():
    parsed = parse_quotes("> grounded. [schemes/a.md, sample_verified]")
    sources = [
        {
            "source": "schemes/a.md",
            "content": "grounded.",
            "data_status": "sample_verified",
        }
    ]
    assert validate_quotes("> grounded. [schemes/a.md, sample_verified]", sources) == (
        verify_quotes(parsed, sources)
    )


# --- a second client attaches without SchemeGPT -------------------------------


def _client_gate() -> str:
    return "ok"


def _client_router(role: str = "answer", max_tokens: int = 1024):
    return object()


def _client_answer(
    question, language="en", profile=None, *, skip_cache=False
) -> dict:
    return {"answer": question, "sources": [], "mode": "live", "language": language}


def _client_validate(answer_text, sources) -> list:
    return []


def _client_egress(question, language="en", profile=None) -> dict:
    return _client_answer(question, language, profile)


async def _client_stream(question, language="en", profile=None):
    yield "event: done\ndata: {}\n\n"


def test_a_second_client_satisfies_the_same_seams():
    client = Spine(
        gate=_client_gate,
        router=_client_router,
        answerer=_client_answer,
        validator=_client_validate,
        egress=_client_egress,
        stream=_client_stream,
    )
    assert isinstance(client.gate, PolicyGate)
    assert isinstance(client.router, ModelRouter)
    assert isinstance(client.answerer, Answerer)
    assert isinstance(client.validator, Validator)
    assert isinstance(client.egress, Egress)
    assert isinstance(client.stream, StreamEgress)
    assert client.egress("q")["answer"] == "q"
