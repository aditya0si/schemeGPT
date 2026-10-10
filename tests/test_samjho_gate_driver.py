"""Wiring tests for the samjho gate driver, run without samjho installed.

The driver (``clients/samjho/run_gate_through_spine.py``) executes samjho's own
``evals.run_eval`` with ``evals.adapter.search`` / ``evals.adapter.answer``
rebound to the spine. samjho is not installed in this repository, so these tests
drive the driver's wiring with signature-faithful stubs -- the same frozen
signatures ``api.answer.answer_question`` and ``api.retriever.search`` declare --
and prove a refusal and a degraded result survive the trip through the binding.

The real end-to-end gate runs outside this repository's test environment; its
recorded result is in ``docs/evidence/SPINE-SECOND-CLIENT.md``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import pytest

from clients.samjho.run_gate_through_spine import (
    SpineRouter,
    SpineTrace,
    _as_exit_code,
    _run_gate,
    install_router,
    main,
    run_samjho_gate,
)

LABEL = "[Ch 1 §1.1 p.2]"


class Samjho:
    """Stub with samjho's frozen signatures that records every call."""

    def __init__(self, answer_result: dict, hits: list[dict] | None = None) -> None:
        self.answer_result = answer_result
        self.hits = hits if hits is not None else [
            {"id": "c1", "chapter_no": 1, "section_no": "1.1", "page_start": 2, "page_end": 2}
        ]
        self.answer_calls: list[dict] = []
        self.search_calls: list[dict] = []

    def answer_question(self, subject, question, chapter_no=None, top_k=None):
        self.answer_calls.append(
            {"subject": subject, "question": question, "chapter_no": chapter_no, "top_k": top_k}
        )
        return self.answer_result

    def search(self, subject, question, chapter_no=None, top_k=None):
        self.search_calls.append(
            {"subject": subject, "question": question, "chapter_no": chapter_no, "top_k": top_k}
        )
        return self.hits


def _citation(chunk_id: str = "c1") -> dict:
    return {
        "chapter_no": 1,
        "section_no": "1.1",
        "page_start": 2,
        "page_end": 2,
        "chunk_id": chunk_id,
        "score": 0.9,
    }


def _written() -> dict:
    return {
        "answer": f'{LABEL} "Silver chloride turns grey in sunlight."',
        "citations": [_citation()],
        "refused": False,
        "provider": "groq",
        "degraded": False,
        "stripped_citations": 0,
    }


def _retrieval_only(degraded: bool = False) -> dict:
    return {
        "answer": f'{LABEL} "Silver chloride turns grey in sunlight."',
        "citations": [_citation()],
        "refused": False,
        "provider": "retrieval-only",
        "degraded": degraded,
        "stripped_citations": 2,
    }


def _refusal() -> dict:
    return {
        "answer": "Not in your material: nothing in the ingested corpus supports an answer.",
        "citations": [],
        "refused": True,
        "refusal_reason": "not_in_corpus",
        "provider": "retrieval-only",
        "degraded": False,
    }


def _normalize_hits(hits):
    return [dict(hit) for hit in hits]


def _normalize_answer(payload):
    return {
        "refused": bool(payload.get("refused")),
        "refusal_reason": payload.get("refusal_reason"),
        "provider": payload.get("provider"),
        "citations": list(payload.get("sources") or []),
        "keys": sorted(payload.keys()),
    }


def _router(result: dict, trace: SpineTrace | None = None):
    stub = Samjho(result)
    router = SpineRouter(
        stub.answer_question,
        stub.search,
        normalize_hits=_normalize_hits,
        normalize_answer=_normalize_answer,
        trace=trace,
    )
    return stub, router


def test_module_imports_without_samjho():
    assert "evals.adapter" not in sys.modules
    assert "evals.run_eval" not in sys.modules


def test_driver_module_has_no_third_party_imports():
    module = sys.modules["clients.samjho.run_gate_through_spine"]
    imported = {name.split(".")[0] for name in vars(module) if not name.startswith("_")}
    assert {"argparse", "importlib", "inspect", "sys"} <= imported
    assert "evals" not in imported
    assert "api" not in imported


def test_answer_routes_through_binding_with_the_frozen_scope():
    stub, router = _router(_written())
    out = router.answer(question="why grey", subject="science", chapter_no=7, top_k=4)
    assert stub.answer_calls == [
        {"subject": "science", "question": "why grey", "chapter_no": 7, "top_k": 4}
    ]
    assert out["refused"] is False
    assert out["provider"] == "groq"


def test_search_routes_through_the_bindings_retrieval_surface():
    stub, router = _router(_written())
    hits = router.search(question="why grey", subject="science", chapter_no=7, top_k=4)
    assert stub.search_calls == [
        {"subject": "science", "question": "why grey", "chapter_no": 7, "top_k": 4}
    ]
    assert hits == [
        {"id": "c1", "chapter_no": 1, "section_no": "1.1", "page_start": 2, "page_end": 2}
    ]


def test_answer_result_keeps_the_written_path():
    _, router = _router(_written())
    payload = router.spine_answer("q", subject="science", chapter_no=1, top_k=4)
    assert payload["path"] == "written"
    assert payload["mode"] == "live"
    assert payload["refused"] is False


def test_refusal_survives_the_spine():
    _, router = _router(_refusal())
    payload = router.spine_answer("q", subject="maths", chapter_no=3, top_k=4)
    assert payload["path"] == "refusal"
    assert payload["refused"] is True
    assert payload["refusal_reason"] == "not_in_corpus"
    assert payload["sources"] == []
    normalized = router.answer(question="q", subject="maths", chapter_no=3, top_k=4)
    assert normalized["refused"] is True
    assert normalized["citations"] == []


def test_degraded_result_survives_the_spine():
    _, router = _router(_retrieval_only(degraded=True))
    payload = router.spine_answer("q", subject="science", chapter_no=1, top_k=4)
    assert payload["degraded"] is True
    assert payload["path"] == "retrieval-only"
    assert payload["mode"] == "degraded"


def test_stripped_citations_survive_the_spine():
    _, router = _router(_retrieval_only())
    payload = router.spine_answer("q", subject="science", chapter_no=1, top_k=4)
    assert payload["stripped_citations"] == 2


def test_each_scope_gets_its_own_binding():
    stub, router = _router(_written())
    router.answer(question="q1", subject="science", chapter_no=1, top_k=4)
    router.answer(question="q2", subject="maths", chapter_no=3, top_k=6)
    assert stub.answer_calls == [
        {"subject": "science", "question": "q1", "chapter_no": 1, "top_k": 4},
        {"subject": "maths", "question": "q2", "chapter_no": 3, "top_k": 6},
    ]
    assert len(router._bindings) == 2


def test_none_top_k_leaves_samjhos_own_default_in_place():
    stub, router = _router(_written())
    router.answer(question="q", subject="science", chapter_no=None, top_k=None)
    assert stub.answer_calls == [
        {"subject": "science", "question": "q", "chapter_no": None, "top_k": None}
    ]


def test_trace_records_refusal_and_degraded_per_subject():
    trace = SpineTrace()
    _, router = _router(_refusal(), trace=trace)
    router.answer(question="q", subject="maths", chapter_no=3, top_k=4)
    _, router = _router(_retrieval_only(degraded=True), trace=trace)
    router.answer(question="q", subject="science", chapter_no=1, top_k=4)
    report = trace.report()
    assert "subject=maths" in report
    assert "refused=1" in report
    assert "degraded=1" in report


# --- installing the router over samjho's adapter ------------------------------


class FakeAdapter:
    SEARCH_ATTRS = ("search", "retrieve")
    ANSWER_ATTRS = ("answer", "answer_question")

    def __init__(self) -> None:
        self.search = lambda **kw: ["raw-search"]
        self.answer = lambda **kw: {"refused": False}

    @staticmethod
    def normalize_hits(hits):
        return list(hits)

    @staticmethod
    def normalize_answer(payload):
        return {"refused": bool(payload.get("refused"))}


def test_install_router_rebinds_adapter_and_direct_reexports():
    adapter = FakeAdapter()
    original_search, original_answer = adapter.search, adapter.answer

    class Runner:
        search = original_search
        answer = original_answer

    _, router = _router(_written())
    install_router(router, adapter, Runner)
    assert adapter.search == router.search
    assert adapter.answer == router.answer
    assert Runner.search == router.search
    assert Runner.answer == router.answer


def test_install_router_leaves_unrelated_run_eval_attributes_alone():
    adapter = FakeAdapter()
    sentinel = lambda **kw: "untouched"

    class Runner:
        search = sentinel

    _, router = _router(_written())
    install_router(router, adapter, Runner)
    assert Runner.search is sentinel


# --- executing samjho's gate --------------------------------------------------


class FakeGate:
    """A stand-in for ``evals.run_eval`` with samjho's documented CLI shape."""

    def __init__(self, code: int = 0, adapter: FakeAdapter | None = None) -> None:
        self.code = code
        self.adapter = adapter
        self.calls: list[list[str]] = []

    def main(self, argv):
        self.calls.append(list(argv))
        if self.adapter is not None:
            self.adapter.answer(question="q", subject="science", chapter_no=1, top_k=4)
        return self.code


def test_run_gate_returns_samjhos_exit_code():
    fake = FakeGate(code=1)
    assert run_samjho_gate(fake) == 1
    assert fake.calls == [["--subjects", "all"]]


def test_run_gate_honours_systemexit():
    class Exiting:
        @staticmethod
        def main(argv):
            raise SystemExit(2)

    assert run_samjho_gate(Exiting) == 2


def test_run_gate_supports_a_no_argument_main():
    class SysArgvGate:
        @staticmethod
        def main():
            return 0

    assert run_samjho_gate(SysArgvGate) == 0


def test_run_gate_raises_when_no_entry_point_exists():
    class Empty:
        pass

    with pytest.raises(RuntimeError):
        run_samjho_gate(Empty)


def test_as_exit_code_reads_objects_and_booleans():
    assert _as_exit_code(None) == 0
    assert _as_exit_code(True) == 0
    assert _as_exit_code(False) == 1
    assert _as_exit_code(7) == 7

    @dataclass
    class Verdict:
        passed: bool

    assert _as_exit_code(Verdict(passed=True)) == 0
    assert _as_exit_code(Verdict(passed=False)) == 1


def test_run_gate_installs_router_before_adapter_is_used(monkeypatch):
    adapter = FakeAdapter()
    fake = FakeGate(code=0, adapter=adapter)
    stub = Samjho(_written())
    monkeypatch.setattr(
        "clients.samjho.run_gate_through_spine._load_callable",
        lambda module_name, attrs: stub.answer_question,
    )
    assert _run_gate(adapter, fake) == 0
    assert fake.calls == [["--subjects", "all"]]
    assert stub.answer_calls  # the fake gate reached samjho through the spine


def test_main_returns_cannot_run_when_samjho_is_unavailable(monkeypatch):
    def boom():
        raise ImportError("no evals module here")

    monkeypatch.setattr(
        "clients.samjho.run_gate_through_spine._import_samjho", boom
    )
    assert main([]) == 2
