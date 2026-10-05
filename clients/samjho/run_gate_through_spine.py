"""Run samjho's own evaluation gate with its adapter routed through the spine.

This is the Phase 7c instrument. It runs *inside samjho's virtualenv* (samjho is
not installed in SchemeGPT) and is the only SchemeGPT code that touches samjho.
It is deliberately built so that the answer is unambiguous: it replaces
samjho's ``evals.adapter.search`` / ``evals.adapter.answer`` with spine-backed
equivalents, then executes samjho's *own* ``evals.run_eval`` over both subjects
and lets samjho print its *own* metric table and gate verdict.

The metrics are never recomputed here. The driver only (a) supplies the client
responses through the spine and (b) forwards samjho's gate exit code, so a
pass/fail is samjho's judgement, not this module's.

What runs through the spine
---------------------------
``evals/run_eval.py`` reaches the client as ``adapter.search(**kwargs)`` and
``adapter.answer(**kwargs)``. Both are rebound to methods of :class:`SpineRouter`:

* ``answer`` -> ``bind_samjho(...).spine.answerer(question)`` using samjho's
  frozen ``api.answer`` callable, then normalised with samjho's own
  ``evals.adapter.normalize_answer`` (so the shape the harness consumes is
  unchanged).
* ``search`` -> ``bind_samjho(...).retrieve(question)``. The spine has no
  retrieval seam (retrieval lives inside the answer unit), so this is the
  binding's published retrieval surface, normalised with samjho's own
  ``evals.adapter.normalize_hits``.

Nothing samjho-specific is imported at module import time: the module is
stdlib + this repository only, so it imports under SchemeGPT's environment and
its wiring is unit-tested there against signature-faithful stubs
(``tests/test_samjho_gate_driver.py``).

Execution (the orchestrator runs this, not the author)
------------------------------------------------------
Run from samjho's checkout root so ``evals`` / ``api`` resolve and any
``evals/golden/*.jsonl`` relative paths resolve, with SchemeGPT on
``PYTHONPATH`` so ``clients`` / ``app`` resolve too. ``DATABASE_URL`` is the
only required override -- samjho's ``api/config.py`` defaults to port 5432
while the measured corpus lives on 5439::

    cd C:/Users/oliad/Desktop/samjho
    PYTHONPATH="C:/Users/oliad/Desktop/SchemeGPT;C:/Users/oliad/Desktop/samjho" \\
        DATABASE_URL="postgresql://samjho:samjho@localhost:5439/samjho" \\
        .venv/Scripts/python.exe \\
        C:/Users/oliad/Desktop/SchemeGPT/clients/samjho/run_gate_through_spine.py

(On Windows the ``PYTHONPATH`` separator is ``;``. If samjho is invoked through
``uv``, substitute ``uv run python`` for the venv interpreter.)

Exit codes: ``0`` only when samjho's gate passes; ``1`` when samjho's gate
fails; ``2`` when the run could not be performed at all (imports, the callables,
or the entry point failed). The gate's printed table is samjho's; this driver
adds only a diagnostic routing trace so a metric difference can be localised to
a subject.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from clients.samjho.binding import bind_samjho

_GATE_ARGV = ("--subjects", "all")
_ENTRY_NAMES = ("main", "cli", "run")
_EXIT_CANNOT_RUN = 2


# ---------------------------------------------------------------------------
# core routing
# ---------------------------------------------------------------------------


class SpineRouter:
    """The two adapter entry points, served by the spine-backed binding.

    A binding freezes ``subject`` / ``chapter_no`` / ``top_k`` at build time, so
    one is built (and cached) per scope the harness asks for; ``question``
    arrives per call. The injected ``answer_question`` / ``search`` are samjho's
    real frozen callables.
    """

    def __init__(
        self,
        answer_question: Callable[..., Any],
        search: Callable[..., Any],
        *,
        normalize_hits: Callable[[Any], list[dict[str, Any]]],
        normalize_answer: Callable[[Any], dict[str, Any]],
        trace: "SpineTrace | None" = None,
    ) -> None:
        self._answer_question = answer_question
        self._search = search
        self._normalize_hits = normalize_hits
        self._normalize_answer = normalize_answer
        self._trace = trace
        self._bindings: dict[tuple[str, Any, Any], Any] = {}

    def _binding(self, subject: str, chapter_no: int | None, top_k: int | None):
        key = (subject, chapter_no, top_k)
        binding = self._bindings.get(key)
        if binding is None:
            # ``top_k`` must be passed explicitly -- including ``None`` -- so a
            # ``None`` reaches samjho's own callable as its default. Omitting it
            # would let ``bind_samjho`` substitute its own 6.
            binding = bind_samjho(
                self._answer_question,
                subject=subject,
                search=self._search,
                chapter_no=chapter_no,
                top_k=top_k,
            )
            self._bindings[key] = binding
        return binding

    def spine_answer(
        self,
        question: str,
        *,
        subject: str,
        chapter_no: int | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """The binding's answer payload, before any samjho normalisation."""
        payload = self._binding(subject, chapter_no, top_k).spine.answerer(question)
        if self._trace is not None:
            self._trace.record_answer(subject, payload)
        return payload

    def spine_hits(
        self,
        question: str,
        *,
        subject: str,
        chapter_no: int | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """The binding's retrieval surface (no spine seam -- see the binding)."""
        hits = self._binding(subject, chapter_no, top_k).retrieve(question)
        if self._trace is not None:
            self._trace.record_search(subject, hits)
        return hits

    def answer(
        self,
        *,
        question: str,
        subject: str,
        chapter_no: int | None = None,
        top_k: int | None = None,
        module_name: str | None = None,
        attr: Any = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        payload = self.spine_answer(
            question, subject=subject, chapter_no=chapter_no, top_k=top_k
        )
        return self._normalize_answer(payload)

    def search(
        self,
        *,
        question: str,
        subject: str,
        chapter_no: int | None = None,
        top_k: int | None = None,
        module_name: str | None = None,
        attr: Any = None,
        **_ignored: Any,
    ) -> list[dict[str, Any]]:
        hits = self.spine_hits(
            question, subject=subject, chapter_no=chapter_no, top_k=top_k
        )
        return self._normalize_hits(hits)


def install_router(router: SpineRouter, adapter: Any, run_eval: Any) -> None:
    """Rebind samjho's adapter (and any direct re-export) to the spine router."""
    original_search = adapter.search
    original_answer = adapter.answer
    adapter.search = router.search
    adapter.answer = router.answer
    for name, original, replacement in (
        ("search", original_search, router.search),
        ("answer", original_answer, router.answer),
    ):
        if getattr(run_eval, name, None) is original:
            setattr(run_eval, name, replacement)


# ---------------------------------------------------------------------------
# diagnostic trace (not gate scoring)
# ---------------------------------------------------------------------------


@dataclass
class SpineTrace:
    """Counts what the spine was asked to do, per subject, for localisation."""

    searches: dict[str, int] = field(default_factory=dict)
    answers: dict[str, int] = field(default_factory=dict)
    refused: dict[str, int] = field(default_factory=dict)
    degraded: dict[str, int] = field(default_factory=dict)
    paths: dict[str, dict[str, int]] = field(default_factory=dict)

    @staticmethod
    def _bump(mapping: dict[str, int], key: str) -> None:
        mapping[key] = mapping.get(key, 0) + 1

    def record_search(self, subject: str, hits: list[dict[str, Any]]) -> None:
        self._bump(self.searches, str(subject))

    def record_answer(self, subject: str, payload: dict[str, Any]) -> None:
        key = str(subject)
        self._bump(self.answers, key)
        if payload.get("refused"):
            self._bump(self.refused, key)
        if payload.get("degraded"):
            self._bump(self.degraded, key)
        path = str(payload.get("path"))
        per_subject = self.paths.setdefault(key, {})
        per_subject[path] = per_subject.get(path, 0) + 1

    def report(self) -> str:
        subjects = sorted(set(self.searches) | set(self.answers))
        lines = ["[spine] routing trace (diagnostic only; gate metrics are samjho's):"]
        if not subjects:
            lines.append("  no routed calls were observed")
            return "\n".join(lines)
        for subject in subjects:
            lines.append(
                f"  subject={subject}: searches={self.searches.get(subject, 0)} "
                f"answers={self.answers.get(subject, 0)} "
                f"refused={self.refused.get(subject, 0)} "
                f"degraded={self.degraded.get(subject, 0)} "
                f"paths={self.paths.get(subject, {})}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# executing samjho's own gate
# ---------------------------------------------------------------------------


def run_samjho_gate(run_eval: Any, argv: list[str] | None = None) -> int:
    """Run samjho's gate and return its exit code.

    Prefers samjho's documented CLI entry (``main`` / ``cli`` / ``run``), which
    prints the metric table and returns/exits the gate verdict. Falls back to
    ``evaluate`` only if no CLI entry exists.
    """
    args = list(_GATE_ARGV if argv is None else argv)
    for name in _ENTRY_NAMES:
        entry = getattr(run_eval, name, None)
        if callable(entry):
            return _invoke_cli(entry, args)
    evaluate = getattr(run_eval, "evaluate", None)
    if callable(evaluate):
        return _invoke_evaluate(evaluate)
    raise RuntimeError(
        "evals.run_eval exposes no callable entry point "
        f"(looked for {', '.join(_ENTRY_NAMES)} and evaluate)"
    )


def _invoke_cli(entry: Callable[..., Any], argv: list[str]) -> int:
    signature = inspect.signature(entry)
    takes_argv = any(
        param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
        for param in signature.parameters.values()
    )
    try:
        if takes_argv:
            result = entry(argv)
        else:
            saved = sys.argv
            sys.argv = ["python -m evals.run_eval", *argv]
            try:
                result = entry()
            finally:
                sys.argv = saved
    except SystemExit as exc:
        return _as_exit_code(exc.code if exc.code is not None else 0)
    return _as_exit_code(result)


def _invoke_evaluate(evaluate: Callable[..., Any]) -> int:
    parameters = inspect.signature(evaluate).parameters
    kwargs: dict[str, Any] = {}
    if "subjects" in parameters:
        kwargs["subjects"] = ["science", "maths"]
    elif "subject" in parameters:
        kwargs["subject"] = "all"
    result = evaluate(**kwargs)
    if isinstance(result, dict) and result:
        for key, value in result.items():
            print(f"[spine] samjho evaluate[{key}] = {value}")
    return _as_exit_code(result)


def _as_exit_code(result: Any) -> int:
    if result is None or result is True:
        return 0
    if result is False:
        return 1
    if isinstance(result, int):
        return int(result)
    for attribute in ("exit_code", "returncode"):
        value = getattr(result, attribute, None)
        if isinstance(value, int):
            return value
    passed = getattr(result, "passed", None)
    if isinstance(passed, bool):
        return 0 if passed else 1
    return 0


# ---------------------------------------------------------------------------
# samjho import (lazy) and entry point
# ---------------------------------------------------------------------------


def _import_samjho() -> tuple[Any, Any]:
    adapter = importlib.import_module("evals.adapter")
    run_eval = importlib.import_module("evals.run_eval")
    return adapter, run_eval


def _load_callable(module_name: str, attrs: Any) -> Callable[..., Any]:
    module = importlib.import_module(module_name)
    for name in attrs:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    raise RuntimeError(f"{module_name} exposes none of {list(attrs)}")


def _run_gate(adapter: Any, run_eval: Any, subjects: str = "all") -> int:
    answer_question = _load_callable("api.answer", adapter.ANSWER_ATTRS)
    search = _load_callable("api.retriever", adapter.SEARCH_ATTRS)
    trace = SpineTrace()
    router = SpineRouter(
        answer_question,
        search,
        normalize_hits=adapter.normalize_hits,
        normalize_answer=adapter.normalize_answer,
        trace=trace,
    )
    install_router(router, adapter, run_eval)
    print(
        "[spine] routed evals.adapter.search / evals.adapter.answer through "
        "clients.samjho.binding; metrics below are samjho's own"
    )
    code = run_samjho_gate(run_eval, argv=["--subjects", subjects])
    print(trace.report())
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--subjects",
        default="all",
        help="passed through to samjho's own gate (default: all)",
    )
    args = parser.parse_args(argv)
    try:
        adapter, run_eval = _import_samjho()
        return _run_gate(adapter, run_eval, subjects=args.subjects)
    except Exception as exc:  # noqa: BLE001 - any import/exec failure is "cannot run"
        print(
            f"[spine] gate could not be run: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return _EXIT_CANNOT_RUN


if __name__ == "__main__":
    raise SystemExit(main())
