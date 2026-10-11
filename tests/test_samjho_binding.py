"""samjho attaches to the spine through the ``clients/samjho`` binding.

samjho is not installed in this repository, so the binding takes its callables
by injection. The stubs below mirror the signatures and return models in the
staged, read-only reference (``.hermes/ref/samjho/``):

* ``api.retriever.search(subject, question, chapter_no=None, top_k=None)``
* ``api.answer.answer_question(subject, question, chapter_no=None, top_k=None)``
  returning an ``AnswerResult`` carrying ``refused`` / ``citations`` /
  ``provider`` / ``degraded`` / ``stripped_citations``.

The tests prove the mapping mechanically: every spine seam is satisfied, the
four logical names bind by name, and samjho's three answer paths plus refusal
and degraded provenance survive the trip through the spine.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, Field

from app.core.seams import (
    Answerer,
    Egress,
    ModelRouter,
    PolicyGate,
    StreamEgress,
    Validator,
)
from app.schemas import VerifiedQuote
from clients.samjho.binding import bind_samjho


class Citation(BaseModel):
    """samjho ``api.answer.Citation`` (fields from the staged copy)."""

    chapter_no: int
    section_no: str
    page_start: int
    page_end: int
    chapter_title: str = ""
    section_title: str = ""
    score: float = 0.0
    chunk_id: str = ""


class AnswerResult(BaseModel):
    """samjho ``api.answer.AnswerResult`` (the fields this binding reads)."""

    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None
    provider: str = "retrieval-only"
    degraded: bool = False
    stripped_citations: int = 0


@dataclass
class Chunk:
    """samjho ``api.retriever.RetrievedChunk`` stand-in (dataclass branch)."""

    id: str
    text: str
    score: float


LABEL = "[Ch 1 §1.1 p.2]"


def _citation(chunk_id: str = "c1") -> Citation:
    return Citation(
        chapter_no=1,
        section_no="1.1",
        page_start=2,
        page_end=2,
        score=0.9,
        chunk_id=chunk_id,
    )


class Samjho:
    """A stub with samjho's frozen signatures that records every call."""

    def __init__(self, result: AnswerResult) -> None:
        self.result = result
        self.answer_calls: list[dict] = []
        self.search_calls: list[dict] = []

    def answer_question(self, subject, question, chapter_no=None, top_k=None):
        self.answer_calls.append(
            {
                "subject": subject,
                "question": question,
                "chapter_no": chapter_no,
                "top_k": top_k,
            }
        )
        return self.result

    def search(self, subject, question, chapter_no=None, top_k=None):
        self.search_calls.append(
            {
                "subject": subject,
                "question": question,
                "chapter_no": chapter_no,
                "top_k": top_k,
            }
        )
        return [Chunk(id="c1", text="silver chloride turns grey", score=0.9)]


def _written() -> AnswerResult:
    return AnswerResult(
        answer=f'{LABEL} "Silver chloride turns grey in sunlight."',
        citations=[_citation()],
        refused=False,
        provider="groq",
        degraded=False,
    )


def _retrieval_only() -> AnswerResult:
    return AnswerResult(
        answer=f'{LABEL} "Silver chloride turns grey in sunlight."',
        citations=[_citation()],
        refused=False,
        provider="retrieval-only",
        degraded=False,
        stripped_citations=2,
    )


def _refusal() -> AnswerResult:
    return AnswerResult(
        answer="Not in your material: nothing in the ingested corpus supports an answer.",
        citations=[],
        refused=True,
        refusal_reason="not_in_corpus",
        provider="retrieval-only",
    )


def _binding(result: AnswerResult, **kwargs):
    samjho = Samjho(result)
    binding = bind_samjho(
        samjho.answer_question,
        subject="science",
        search=samjho.search,
        chapter_no=7,
        top_k=4,
        **kwargs,
    )
    return samjho, binding


def test_every_spine_seam_is_satisfied():
    _, binding = _binding(_written())
    spine = binding.spine
    assert isinstance(spine.gate, PolicyGate)
    assert isinstance(spine.router, ModelRouter)
    assert isinstance(spine.answerer, Answerer)
    assert isinstance(spine.validator, Validator)
    assert isinstance(spine.egress, Egress)
    assert isinstance(spine.stream, StreamEgress)


def test_logical_names_bind_onto_samjho_real_signature():
    samjho, binding = _binding(_written())
    binding.spine.answerer("why is the sky blue")
    assert samjho.answer_calls == [
        {
            "subject": "science",
            "question": "why is the sky blue",
            "chapter_no": 7,
            "top_k": 4,
        }
    ]


def test_logical_names_bind_onto_renamed_parameters():
    captured: list[tuple] = []

    class Renamed:
        def answer_question(self, query, subject_id, chapter_number=None, limit=None):
            captured.append((query, subject_id, chapter_number, limit))
            return _written()

    binding = bind_samjho(
        Renamed().answer_question,
        subject="science",
        chapter_no=7,
        top_k=4,
    )
    binding.spine.answerer("q")
    assert captured == [("q", "science", 7, 4)]


def test_retrieve_binds_samjho_search_and_normalises_hits():
    samjho, binding = _binding(_written())
    hits = binding.retrieve("why grey")
    assert samjho.search_calls == [
        {
            "subject": "science",
            "question": "why grey",
            "chapter_no": 7,
            "top_k": 4,
        }
    ]
    assert hits == [{"id": "c1", "text": "silver chloride turns grey", "score": 0.9}]


def test_written_answer_path_survives():
    _, binding = _binding(_written())
    payload = binding.spine.answerer("q")
    assert payload["path"] == "written"
    assert payload["mode"] == "live"
    assert payload["provider"] == "groq"
    assert payload["refused"] is False
    assert payload["degraded"] is False
    assert payload["answer"].startswith(LABEL)


def test_retrieval_only_path_survives():
    _, binding = _binding(_retrieval_only())
    payload = binding.spine.answerer("q")
    assert payload["path"] == "retrieval-only"
    assert payload["mode"] == "degraded"
    assert payload["provider"] == "retrieval-only"
    assert payload["refused"] is False


def test_refusal_path_survives():
    _, binding = _binding(_refusal())
    payload = binding.spine.answerer("q")
    assert payload["path"] == "refusal"
    assert payload["refused"] is True
    assert payload["refusal_reason"] == "not_in_corpus"
    assert payload["provider"] == "retrieval-only"
    assert payload["sources"] == []


def test_degraded_result_survives():
    degraded = _retrieval_only()
    degraded.degraded = True
    _, binding = _binding(degraded)
    payload = binding.spine.answerer("q")
    assert payload["degraded"] is True
    assert payload["path"] == "retrieval-only"


def test_stripped_citations_survive():
    _, binding = _binding(_retrieval_only())
    assert binding.spine.answerer("q")["stripped_citations"] == 2


def test_citations_map_onto_the_validated_quote_shape():
    _, binding = _binding(_written())
    payload = binding.spine.answerer("q")
    records = binding.spine.validator(payload["answer"], payload["sources"])
    assert len(records) == 1
    quote = VerifiedQuote(**records[0])
    assert quote.source == LABEL
    assert quote.verified is True
    assert quote.matched_source == "c1"


def test_validator_marks_absent_citations_unverified():
    _, binding = _binding(_written())
    payload = binding.spine.answerer("q")
    records = binding.spine.validator("no citation marker here", payload["sources"])
    assert VerifiedQuote(**records[0]).verified is False


def test_refusal_has_no_fabricated_quotes():
    _, binding = _binding(_refusal())
    payload = binding.spine.answerer("q")
    assert binding.spine.validator(payload["answer"], payload["sources"]) == []


def test_egress_seam_returns_the_answer_payload():
    _, binding = _binding(_written())
    payload = binding.spine.egress("q")
    assert payload["answer"].startswith(LABEL)
    assert payload["path"] == "written"


def test_stream_seam_frames_the_answer_as_sse():
    _, binding = _binding(_written())

    async def collect():
        return [block async for block in binding.spine.stream("q")]

    blocks = asyncio.run(collect())
    assert blocks[0].startswith("event: sources\n")
    assert blocks[1].startswith("event: token\n")
    assert blocks[-1].startswith("event: done\n")
    assert '"refused": false' in blocks[-1]


def test_gate_router_and_stream_are_injectable():
    default_spine = _binding(_written())[1].spine
    assert default_spine.gate() == "ok"
    with pytest.raises(NotImplementedError):
        default_spine.router()

    custom = bind_samjho(
        Samjho(_written()).answer_question,
        subject="science",
        gate=lambda: "breaker",
        router=lambda role="answer", max_tokens=1024: "client",
    )
    assert custom.spine.gate() == "breaker"
    assert custom.spine.router("fast", 64) == "client"
