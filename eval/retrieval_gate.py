"""Deterministic source-retrieval quality gate for SchemeGPT.

Unlike the optional live generation judge, this gate needs no LLM key. It evaluates
the production hybrid retriever against source labels in ``questions.json`` and
fails on missing rows, retrieval errors, or metric regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from eval.run_eval import QUESTIONS_FILE, RESULTS_DIR, _load_questions

HIT_RATE_FLOOR = 0.85
MRR_FLOOR = 0.60
DEFAULT_TOP_K = 4
MIN_LABELLED_CASES = 16
RESULTS_FILE = RESULTS_DIR / "retrieval_scores.json"


def _source_id(value: Any) -> str:
    return str(value or "").replace("\\", "/").removeprefix("./").lstrip("/").casefold()


def evaluate_cases(cases: list[dict], retriever, top_k: int = DEFAULT_TOP_K) -> dict:
    """Evaluate labelled cases with exact source provenance at ``top_k``."""
    labelled = [case for case in cases if case.get("expected_sources")]
    rows: list[dict] = []
    reciprocal_ranks: list[float] = []
    hits = 0
    errors = 0

    for index, case in enumerate(labelled, start=1):
        expected = {_source_id(source) for source in case["expected_sources"]}
        row = {
            "id": case.get("id") or f"case-{index}",
            "question": case["question"],
            "expected_sources": sorted(expected),
            "retrieved_sources": [],
            "rank": None,
            "hit": False,
            "error": None,
        }
        try:
            docs = retriever.invoke(case["question"])
            retrieved = [
                _source_id(getattr(doc, "metadata", {}).get("source"))
                for doc in docs[:top_k]
            ]
            row["retrieved_sources"] = retrieved
            rank = next(
                (position for position, source in enumerate(retrieved, start=1) if source in expected),
                None,
            )
            row["rank"] = rank
            row["hit"] = rank is not None
            hits += int(rank is not None)
            reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        except Exception as exc:
            errors += 1
            row["error"] = f"{type(exc).__name__}: retrieval failed"
        rows.append(row)

    completed = len(labelled) - errors
    return {
        "dataset": str(QUESTIONS_FILE.name),
        "top_k": top_k,
        "labelled_cases": len(labelled),
        "completed_cases": completed,
        "error_count": errors,
        "hit_rate_at_k": hits / completed if completed else None,
        "mrr_at_k": sum(reciprocal_ranks) / completed if completed else None,
        "rows": rows,
    }


def gate_failures(summary: dict) -> list[str]:
    failures: list[str] = []
    labelled = int(summary.get("labelled_cases") or 0)
    completed = int(summary.get("completed_cases") or 0)
    errors = int(summary.get("error_count") or 0)
    if labelled == 0:
        failures.append("coverage: no expected_sources labels found")
    elif labelled < MIN_LABELLED_CASES:
        failures.append(
            f"coverage: {labelled} labelled cases; required {MIN_LABELLED_CASES}"
        )
    elif completed != labelled:
        failures.append(f"coverage: {completed}/{labelled} labelled cases completed")
    if errors:
        failures.append(f"errors: {errors} retrieval case(s) failed")
    for name, floor in (("hit_rate_at_k", HIT_RATE_FLOOR), ("mrr_at_k", MRR_FLOOR)):
        value = summary.get(name)
        if value is None:
            failures.append(f"{name}: missing")
        elif float(value) < floor:
            failures.append(f"{name}: {float(value):.3f} < {floor:.2f}")
    return failures


def run(
    top_k: int = DEFAULT_TOP_K,
    output: Path = RESULTS_FILE,
    corpus_generation: str | None = None,
) -> tuple[dict, list[str]]:
    from app.db import read_corpus_generation
    from app.rag import get_retriever

    if corpus_generation is None:
        corpus_generation = read_corpus_generation()
    if not corpus_generation:
        raise RuntimeError(
            "No active corpus generation recorded; ingest the corpus before "
            "running the retrieval gate."
        )
    # Exercise the production generation-bound retriever (post-ingestion), not
    # an unbound one that could score rows from a different corpus.
    summary = evaluate_cases(
        _load_questions(None), get_retriever(corpus_generation), top_k=top_k
    )
    summary["corpus_generation"] = corpus_generation
    failures = gate_failures(summary)
    summary["gate"] = {
        "passed": not failures,
        "failures": failures,
        "floors": {"hit_rate_at_k": HIT_RATE_FLOOR, "mrr_at_k": MRR_FLOOR},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate production hybrid retrieval without an LLM key.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--output", type=Path, default=RESULTS_FILE)
    args = parser.parse_args(argv)
    if args.top_k < 1:
        parser.error("--top-k must be positive")
    try:
        summary, failures = run(args.top_k, args.output)
    except RuntimeError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Retrieval evaluation: {summary['completed_cases']}/{summary['labelled_cases']} complete, "
        f"hit@{summary['top_k']}={summary['hit_rate_at_k']}, mrr@{summary['top_k']}={summary['mrr_at_k']}"
    )
    if failures:
        for failure in failures:
            print(f"GATE FAILED: {failure}")
        return 1
    print(f"Gate passed. Results: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
