"""Live generation and provider-neutral LLM-judge harness for SchemeGPT.

Run from the project root:

    python -m eval.run_eval [--limit N]

Reuses the production pipeline - ``app.rag.answer`` for inference,
``app.rag.get_llm`` (Groq) as the judge LLM and ``app.db.get_embeddings``
(local HuggingFace) as the judge embeddings - so every LLM call goes to the
Groq free tier and no OpenAI or paid embedding API is ever used. Cases may
carry optional ``language`` (``"en"``/``"hi"``) and ``profile`` fields in
``eval/questions.json``; both are passed straight to the production pipeline.

Generates:
    eval/results/report.md     publishable Markdown report
    eval/results/scores.json   machine-readable per-case and aggregate scores

A failure case is any case whose ``faithfulness`` or ``answer_relevancy``
score is below FAILURE_THRESHOLD (0.70), or a case where the RAG pipeline or
the model judge raised an error. If ``app.rag.answer`` falls back to demo mode
(missing/invalid/rate-limited Groq call), the case is recorded as a pipeline
error: it is never passed to the judge and never given faithfulness or
answer-relevancy scores, and it stays visible under Failure Cases. The
threshold is a project triage threshold, not a universal quality claim.

This module only executes when run as ``python -m eval.run_eval``; importing
it does not run anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = EVAL_DIR.parent
RESULTS_DIR = EVAL_DIR / "results"
QUESTIONS_FILE = EVAL_DIR / "questions.json"
REPORT_FILE = RESULTS_DIR / "report.md"
SCORES_FILE = RESULTS_DIR / "scores.json"
HISTORY_FILE = RESULTS_DIR / "history.jsonl"

# Single project-wide triage threshold. Any metric below this value (or
# missing because of an evaluation error) flags a failure case.
FAILURE_THRESHOLD = 0.70

# Free-tier pacing: the answer pipeline (normalize + retrieval + answer) is
# ~2-6k tokens per case against a shared 8k tokens/minute quota (agent-routed
# cases burst). A 40 s gap keeps the sustained rate comfortably under it;
# the judge phase uses one bounded request per successful case.
INTER_CASE_SLEEP_SECONDS = 40.0
RATE_LIMIT_BACKOFF_SECONDS = 65.0

# Regression-gate floors (per aggre gate with --gate). Stricter than the
# per-case triage threshold; failing a floor makes the command exit non-zero.
GATE_FLOORS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.70,
}
GATE_METRICS = tuple(GATE_FLOORS)

# Error recorded when app.rag.answer fell back to demo mode (a missing, invalid
# or rate-limited Groq call returned a pre-made demo answer). Demo answers are
# never scored by the judge and are reported as failure cases. The message is
# deliberately safe and actionable; it never contains provider error details
# or secrets.
DEMO_FALLBACK_ERROR = (
    "Live RAG returned demo fallback; provide a valid GROQ_API_KEY "
    "before evaluating"
)

# The explicit judge returns four bounded metrics. Only answer-quality metrics
# are gated; context metrics are reported for retrieval diagnosis.
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


def check_gate(
    aggregates: dict,
    *,
    scored_count: int | None = None,
    expected_count: int | None = None,
    error_count: int = 0,
) -> list[str]:
    """Return aggregate, completeness, and infrastructure gate failures.

    Aggregate means exclude missing values for diagnosis, but the regression
    gate must never pass on a successful subset. When counts are supplied,
    every expected case must have a complete score row and zero errors.
    """
    failures: list[str] = []
    if expected_count is not None:
        actual = 0 if scored_count is None else scored_count
        if actual != expected_count:
            failures.append(
                f"coverage: {actual}/{expected_count} cases completely scored"
            )
    if error_count:
        failures.append(f"errors: {error_count} case(s) failed pipeline or evaluation")
    for name, floor in GATE_FLOORS.items():
        value = aggregates.get(name)
        if value is None:
            failures.append(f"{name}: missing (no score)")
        elif value < floor:
            failures.append(f"{name}: {value:.3f} < {floor:.2f}")
    return failures

class EvalError(RuntimeError):
    """Expected, user-actionable setup/input error (shown without traceback)."""


def _ensure_project_on_path() -> None:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))


def _load_questions(limit: int | None) -> list[dict[str, Any]]:
    if not QUESTIONS_FILE.is_file():
        raise EvalError(f"Questions file not found: {QUESTIONS_FILE}")
    try:
        data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalError(f"Invalid JSON in {QUESTIONS_FILE}: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("questions", [])
    if not isinstance(data, list):
        raise EvalError(f"{QUESTIONS_FILE} must contain a JSON list of cases.")
    questions = [
        item
        for item in data
        if isinstance(item, dict)
        and isinstance(item.get("question"), str)
        and item["question"].strip()
    ]
    if limit is not None:
        questions = questions[:limit]
    if not questions:
        raise EvalError("No questions with a non-empty 'question' field were found.")
    return questions


def _run_pipeline(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ask the production RAG pipeline; record per-case pipeline errors.

    Each case may carry optional ``language`` (``"en"``/``"hi"``) and
    ``profile`` (a ProfileData-shaped dict) fields that are passed through to
    ``app.rag.answer``, so Hindi and profile-aware cases exercise the same
    production path as the UI. Cases without these fields run as plain English
    questions, exactly as before.

    A response in demo fallback mode (``mode == "demo"``: a missing, invalid
    or rate-limited Groq call fell back to a pre-made answer) is treated as a
    pipeline/evaluation error. The demo answer is not a live RAG result and is
    never scored by the judge: the row keeps its error marker so ``run()``
    excludes it from the scored dataset while it stays visible under Failure
    Cases in the report.
    """
    from app.rag import answer
    from app.schemas import ProfileData

    rows: list[dict[str, Any]] = []
    for item in questions:
        question = item["question"]
        language = str(item.get("language") or "en")
        profile_raw = item.get("profile")
        profile = (
            ProfileData(**profile_raw)
            if isinstance(profile_raw, dict)
            else None
        )
        row: dict[str, Any] = {
            "question": question,
            "reference": item.get("reference", ""),
            "language": language,
            "profile": profile_raw if isinstance(profile_raw, dict) else None,
            "answer": "",
            "contexts": [],
            "sources": [],
            "error": None,
            "metrics": None,
        }
        try:
            result = answer(question, language=language, profile=profile)
            if result.get("mode") == "demo":
                # Most common cause: the shared free-tier per-minute token
                # limit tripped (the answer chain + normalization are ~2k
                # tokens). Back off once before giving up on the case.
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                result = answer(question, language=language, profile=profile)
            if result.get("mode") == "demo":
                row["answer"] = result.get("answer", "")
                row["error"] = DEMO_FALLBACK_ERROR
            else:
                sources = result.get("sources", [])
                row["answer"] = result.get("answer", "")
                row["contexts"] = [s.get("content", "") for s in sources]
                row["sources"] = sources
        except Exception as exc:  # DB/embedding/chain failure - record and keep going
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        # Steady pacing keeps ~20 sequential cases inside the free tier's
        # tokens/minute window instead of bursting all at once.
        time.sleep(INTER_CASE_SLEEP_SECONDS)
    return rows


def _clean_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(score) else score


def _parse_judge_scores(raw: str) -> dict[str, float]:
    """Parse and validate one model-judge JSON response."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("judge response did not contain a JSON object")
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge response was not valid JSON: {exc}") from exc

    missing = [name for name in METRICS if name not in payload]
    if missing:
        raise ValueError("judge response missing metrics: " + ", ".join(missing))

    scores: dict[str, float] = {}
    for name in METRICS:
        score = _clean_score(payload[name])
        if score is None:
            raise ValueError(f"judge metric {name} was not numeric")
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"judge metric {name} must be between 0 and 1")
        scores[name] = score
    return scores


def _score_rows(rows: list[dict[str, Any]]) -> None:
    """Score live answers with one explicit, provider-neutral LLM judge call."""
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    from app.rag import get_llm

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a strict RAG evaluator. Score each metric from 0 to 1. "
                "faithfulness measures whether the answer is supported by context; "
                "answer_relevancy measures whether it answers the question; "
                "context_precision measures whether retrieved context is relevant; "
                "context_recall measures whether context covers the reference answer. "
                "Return only a JSON object with exactly these numeric keys: "
                "faithfulness, answer_relevancy, context_precision, context_recall.",
            ),
            (
                "human",
                "Question:\n{question}\n\nReference answer:\n{reference}\n\n"
                "Retrieved context:\n{contexts}\n\nCandidate answer:\n{answer}",
            ),
        ]
    )
    chain = prompt | get_llm("judge") | StrOutputParser()

    for row in rows:
        try:
            raw = chain.invoke(
                {
                    "question": row["question"],
                    "reference": row["reference"],
                    "contexts": "\n\n---\n\n".join(row["contexts"]),
                    "answer": row["answer"],
                }
            )
            row["metrics"] = _parse_judge_scores(raw)
        except Exception as exc:
            row["metrics"] = {name: None for name in METRICS}
            row["error"] = f"evaluation error: {type(exc).__name__}: {exc}"


def _build_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        metrics = row.get("metrics") or {}
        cases.append(
            {
                "question": row["question"],
                "reference": row.get("reference", ""),
                "answer": row.get("answer", ""),
                "contexts": row.get("contexts", []),
                "sources": row.get("sources", []),
                "faithfulness": metrics.get("faithfulness"),
                "answer_relevancy": metrics.get("answer_relevancy"),
                "context_precision": metrics.get("context_precision"),
                "context_recall": metrics.get("context_recall"),
                "error": row.get("error"),
            }
        )
    return cases


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, float | None]:
    aggregate: dict[str, float | None] = {}
    for name in METRICS:
        values = [case[name] for case in cases if case[name] is not None]
        aggregate[name] = sum(values) / len(values) if values else None
    return aggregate


def _is_failure(case: dict[str, Any]) -> bool:
    if case["error"] is not None:
        return True
    return any(
        case[name] is None or case[name] < FAILURE_THRESHOLD for name in METRICS
    )


# --- Markdown helpers (safe enough for ordinary text) -------------------------


def _md_escape(text: str) -> str:
    """Escape text for inline Markdown: backslashes, backticks, pipes, angle brackets."""
    text = str(text)
    text = text.replace("\\", "\\\\").replace("`", "\\`")
    text = text.replace("|", "\\|").replace("<", "\\<").replace(">", "\\>")
    return " ".join(text.splitlines())


def _md_fence(text: str) -> str:
    return str(text).replace("```", "'''").rstrip()


def _fmt(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.3f}"


def _status(case: dict[str, Any]) -> str:
    return "FAIL" if _is_failure(case) else "pass"


def _write_report(
    cases: list[dict[str, Any]],
    aggregate: dict[str, float | None],
    generated_at: str,
    total_count: int,
    limit: int | None,
) -> None:
    lines: list[str] = []
    lines.append("# SchemeGPT Live Generation Evaluation Report")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}` (UTC)")
    lines.append(f"- Cases evaluated: {len(cases)} of {total_count}")
    if limit is not None:
        lines.append(f"- Command: `python -m eval.run_eval --limit {limit}`")
    else:
        lines.append("- Command: `python -m eval.run_eval`")
    lines.append(
        f"- Threshold: **{FAILURE_THRESHOLD:.2f}** - any `faithfulness` or "
        "`answer_relevancy` score below this value (or a missing score) is a "
        "failure case."
    )
    lines.append(
        "- Judge LLM: Groq (settings.groq_model, free tier); "
        "embeddings: local sentence-transformers."
    )
    lines.append("")
    lines.append("## Aggregate Scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("| --- | --- |")
    for name in METRICS:
        lines.append(f"| {name} | {_fmt(aggregate[name])} |")
    lines.append("")

    previous = _previous_aggregate()
    if previous:
        lines.append("## Delta vs previous run")
        lines.append("")
        lines.append("| Metric | This run | Previous | Delta |")
        lines.append("| --- | --- | --- | --- |")
        for name in METRICS:
            now = aggregate.get(name)
            then = previous.get(name)
            if now is None or then is None:
                lines.append(f"| {name} | {_fmt(now)} | {_fmt(then)} | n/a |")
            else:
                lines.append(
                    f"| {name} | {_fmt(now)} | {_fmt(then)} | {now - then:+.3f} |"
                )
        lines.append("")
    lines.append("## Per-Question Scores")
    lines.append("")
    lines.append(
        "| # | Question | faithfulness | answer_relevancy | context_precision "
        "| context_recall | Status |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for index, case in enumerate(cases, start=1):
        lines.append(
            f"| {index} | {_md_escape(case['question'])} | "
            f"{_fmt(case['faithfulness'])} | {_fmt(case['answer_relevancy'])} | "
            f"{_fmt(case['context_precision'])} | {_fmt(case['context_recall'])} | "
            f"{_status(case)} |"
        )
    lines.append("")
    lines.append("## Failure Cases")
    lines.append("")
    failures = [case for case in cases if _is_failure(case)]
    if not failures:
        lines.append("None. All cases scored at or above the threshold.")
    else:
        lines.append(
            f"{len(failures)} case(s) flagged: score below the threshold "
            "or an evaluation error."
        )
        lines.append("")
        for index, case in enumerate(failures, start=1):
            lines.append(f"### {index}. {_md_escape(case['question'])}")
            lines.append("")
            lines.append(f"- **Question**: {_md_escape(case['question'])}")
            if case["reference"]:
                lines.append(f"- **Reference**: {_md_escape(case['reference'])}")
            lines.append("- **Answer**:")
            lines.append("")
            lines.append("  ```text")
            lines.append("  " + _md_fence(case["answer"] or "(no answer produced)"))
            lines.append("  ```")
            lines.append("")
            lines.append(f"- **faithfulness**: {_fmt(case['faithfulness'])}")
            lines.append(f"- **answer_relevancy**: {_fmt(case['answer_relevancy'])}")
            if case["error"]:
                lines.append(f"- **Error**: {_md_escape(case['error'])}")
            lines.append("")
            lines.append("- **Retrieved sources/contexts**:")
            if not case["contexts"]:
                lines.append("  - (no contexts retrieved)")
            else:
                for ctx_index, ctx in enumerate(case["contexts"], start=1):
                    source = ""
                    if ctx_index - 1 < len(case["sources"]):
                        source = case["sources"][ctx_index - 1].get("source", "")
                    lines.append(
                        f"  {ctx_index}. {_md_escape(source or '(source unknown)')}:"
                    )
                    lines.append("")
                    lines.append("     ```text")
                    lines.append("     " + _md_fence(ctx))
                    lines.append("     ```")
            lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        f"- The threshold of **{FAILURE_THRESHOLD:.2f}** is a project triage "
        "threshold, not a universal quality claim."
    )
    lines.append(
        "- Live answers and judge calls consume Groq free-tier quota; "
        "`--limit N` provides cheap/free partial runs."
    )
    lines.append("- Per-case scores are also available in `scores.json`.")
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_scores(
    cases: list[dict[str, Any]],
    aggregate: dict[str, float | None],
    generated_at: str,
    total_count: int,
    limit: int | None,
) -> None:
    payload = {
        "generated_at": generated_at,
        "threshold": FAILURE_THRESHOLD,
        "metrics": list(METRICS),
        "cases_total": total_count,
        "limit": limit,
        "aggregate": aggregate,
        "cases": cases,
    }
    SCORES_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _config_fingerprint() -> dict:
    """Which model/retriever configuration produced this run's scores."""
    from app.config import ROOT_DIR, settings
    from app.rag import PROMPT_VERSION

    corpus = {}
    for name in ("schemes", "states", "myscheme"):
        directory = ROOT_DIR / "data" / name
        corpus[name] = len(list(directory.glob("*.md"))) if directory.is_dir() else 0

    return {
        "prompt_version": PROMPT_VERSION,
        "embedding_model": settings.embedding_model,
        "groq_model": settings.groq_model,
        "groq_fast_model": settings.groq_fast_model,
        "reranker_enabled": settings.enable_reranker,
        "retriever": "hybrid",
        "corpus": corpus,
    }


def _append_history(
    aggregate: dict, generated_at: str, limit: int | None, label: str | None = None
) -> None:
    """Append one JSON line per run; used for delta comparisons."""
    try:
        with HISTORY_FILE.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "generated_at": generated_at,
                        "label": label,
                        "limit": limit,
                        "config": _config_fingerprint(),
                        "aggregate": aggregate,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as exc:  # history is best-effort, never blocks a run
        print(f"warning: could not write history: {type(exc).__name__}: {exc}")


def _previous_aggregate() -> dict | None:
    """Aggregate scores from the most recent completed run, if any."""
    if not HISTORY_FILE.is_file():
        return None
    lines = [ln for ln in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1]).get("aggregate")
    except (IndexError, json.JSONDecodeError):
        return None


def run(limit: int | None = None, gate: bool = False, label: str | None = None) -> dict[str, Any]:
    _ensure_project_on_path()

    from app.config import settings

    # The eval must measure the live pipeline, never the semantic cache:
    # cached answers carry stale/foreign sources and would poison scoring.
    settings.enable_semantic_cache = False

    if not settings.groq_api_key.strip():
        raise EvalError(
            "GROQ_API_KEY is missing or empty. Set GROQ_API_KEY in your "
            "environment or in .env (see .env.example), then re-run."
        )

    all_questions = _load_questions(None)
    questions = all_questions[:limit] if limit is not None else all_questions
    dataset_total = len(all_questions)
    rows = _run_pipeline(questions)

    ok_rows = [row for row in rows if row["error"] is None]
    if not ok_rows:
        # Every case fell back to demo mode (missing/invalid/rate-limited Groq
        # key, or an unreachable database). Fail clearly instead of publishing
        # a report full of unscored demo fallbacks. No provider details leak.
        raise EvalError(
            "All cases fell back to demo mode; the live RAG path produced no "
            "answers. Evaluation requires a valid GROQ_API_KEY and a running, "
            "ingested database (docker compose up -d db). Set GROQ_API_KEY in "
            "your environment or .env, then re-run."
        )
    _score_rows(ok_rows)

    cases = _build_cases(rows)
    aggregate = _aggregate(cases)
    failure_cases = [case for case in cases if _is_failure(case)]
    scored_count = sum(
        case["error"] is None
        and all(case[name] is not None for name in METRICS)
        for case in cases
    )
    error_count = sum(case["error"] is not None for case in cases)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_report(
        cases=cases,
        aggregate=aggregate,
        generated_at=generated_at,
        total_count=dataset_total,
        limit=limit,
    )
    _write_scores(cases, aggregate, generated_at, dataset_total, limit)
    _append_history(aggregate, generated_at, limit, label)

    gate_failures = (
        check_gate(
            aggregate,
            scored_count=scored_count,
            expected_count=len(questions),
            error_count=error_count,
        )
        if gate
        else []
    )

    return {
        "generated_at": generated_at,
        "cases_total": dataset_total,
        "cases_evaluated": len(questions),
        "cases_scored": scored_count,
        "aggregate": aggregate,
        "failure_count": len(failure_cases),
        "gate_failures": gate_failures,
        "report": str(REPORT_FILE),
        "scores": str(SCORES_FILE),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run_eval",
        description="Run the live generation evaluation harness for SchemeGPT "
        "(Groq judge LLM + local HuggingFace embeddings).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Evaluate only the first N questions (cheap/free run). "
        "Default: all questions.",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Fail unless every selected case is completely scored with zero "
        "errors and aggregate floors are met (faithfulness >= 0.85, "
        "answer_relevancy >= 0.70).",
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        metavar="TEXT",
        help="Tag this run in eval/results/history.jsonl and the report "
        "(e.g. 'baseline-42docs', 'scaled-723docs').",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    try:
        summary = run(limit=args.limit, gate=args.gate, label=args.label)
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(
            f"ERROR: evaluation failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "Is the database running (docker compose up -d db)? "
            "Is GROQ_API_KEY valid and Groq quota available?",
            file=sys.stderr,
        )
        return 1

    print(
        "Evaluation complete: "
        f"{summary['cases_evaluated']}/{summary['cases_total']} selected, "
        f"{summary['cases_scored']} completely scored, "
        f"{summary['failure_count']} failure case(s)."
    )
    if summary["gate_failures"]:
        print("GATE FAILED:", file=sys.stderr)
        for failure in summary["gate_failures"]:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"Report: {summary['report']}")
    print(f"Scores: {summary['scores']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
