"""Iteration 2: RAGAS evaluation harness for SchemeGPT.

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
a RAGAS metric raised an error. If ``app.rag.answer`` falls back to demo mode
(missing/invalid/rate-limited Groq call), the case is recorded as a pipeline
error: it is never passed to RAGAS and never given faithfulness or
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
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = EVAL_DIR.parent
RESULTS_DIR = EVAL_DIR / "results"
QUESTIONS_FILE = EVAL_DIR / "questions.json"
REPORT_FILE = RESULTS_DIR / "report.md"
SCORES_FILE = RESULTS_DIR / "scores.json"

# Single project-wide triage threshold. Any metric below this value (or
# missing because of an evaluation error) flags a failure case.
FAILURE_THRESHOLD = 0.70

# Error recorded when app.rag.answer fell back to demo mode (a missing, invalid
# or rate-limited Groq call returned a pre-made demo answer). Demo answers are
# never scored by RAGAS and are reported as failure cases. The message is
# deliberately safe and actionable; it never contains provider error details
# or secrets.
DEMO_FALLBACK_ERROR = (
    "Live RAG returned demo fallback; provide a valid GROQ_API_KEY "
    "before evaluating"
)

# RAGAS 0.2.x metric names. `faithfulness` and `answer_relevancy` are the
# 0.2.15 names; newer-only aliases are deliberately not used.
METRICS = ("faithfulness", "answer_relevancy")

# Parses the executor error records that RAGAS 0.2.x logs when a metric fails,
# e.g. `Exception raised in Job[3]: AuthenticationError(invalid api key)`.
_JOB_ERROR_RE = re.compile(r"Exception raised in Job\[(\d+)\]:\s*(.*)")


class EvalError(RuntimeError):
    """Expected, user-actionable setup/input error (shown without traceback)."""


class _ErrorCollector(logging.Handler):
    """Collects RAGAS executor error records and maps them back to rows."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._messages: list[tuple[int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        # Depends on the RAGAS 0.2.15 executor log format ("Exception raised in
        # Job[N]: ..."); pinned-version internal behavior, not a public API.
        match = _JOB_ERROR_RE.search(record.getMessage())
        if match:
            self._messages.append((int(match.group(1)), match.group(2).strip()))

    def row_errors(self, num_metrics: int, row_index: int) -> list[str]:
        # Jobs are submitted row-major: counter = num_metrics * row + metric_idx.
        return [
            message
            for counter, message in self._messages
            if counter // num_metrics == row_index
        ]


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
    never scored by RAGAS: the row keeps its error marker so ``run()``
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
    return rows


def _clean_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(score) else score


def _score_rows(rows: list[dict[str, Any]]) -> None:
    """Run RAGAS 0.2.15 synchronously with the app's Groq LLM + local embeddings."""
    from datasets import Dataset as HFDataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    from app.db import get_embeddings
    from app.rag import get_llm

    # RAGAS 0.2.x v2 dataset columns: question / answer / contexts / ground_truth.
    hf_dataset = HFDataset.from_list(
        [
            {
                "question": row["question"],
                "answer": row["answer"],
                "contexts": row["contexts"],
                "ground_truth": row["reference"],
            }
            for row in rows
        ]
    )

    collector = _ErrorCollector()
    logging.getLogger("ragas.executor").addHandler(collector)
    try:
        result = evaluate(
            dataset=hf_dataset,
            metrics=[faithfulness, answer_relevancy],
            llm=get_llm(),
            embeddings=get_embeddings(),
            raise_exceptions=False,
            show_progress=True,
        )
    finally:
        logging.getLogger("ragas.executor").removeHandler(collector)

    num_metrics = len(METRICS)
    for index, row in enumerate(rows):
        if index >= len(result.scores):
            # Guard before indexing: RAGAS may return fewer score rows than
            # input rows. Keep report rows aligned by recording explicit None
            # metrics plus an explanatory error instead of silently skipping.
            row["metrics"] = {name: None for name in METRICS}
            row["error"] = "evaluation error: RAGAS returned no score for this row"
            continue
        scores = result.scores[index]
        metrics = {name: _clean_score(scores.get(name)) for name in METRICS}
        row["metrics"] = metrics
        problems: list[str] = []
        failed = [name for name in METRICS if metrics[name] is None]
        if failed:
            problems.append("RAGAS did not return a score for " + ", ".join(failed))
        problems.extend(collector.row_errors(num_metrics, index))
        if problems:
            row["error"] = "evaluation error: " + "; ".join(problems)


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
    lines.append("# SchemeGPT RAGAS Evaluation Report")
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
        "- Judge LLM: Groq (`llama-3.3-70b-versatile`, free tier); "
        "embeddings: local `all-MiniLM-L6-v2`."
    )
    lines.append("")
    lines.append("## Aggregate Scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("| --- | --- |")
    for name in METRICS:
        lines.append(f"| {name} | {_fmt(aggregate[name])} |")
    lines.append("")
    lines.append("## Per-Question Scores")
    lines.append("")
    lines.append("| # | Question | faithfulness | answer_relevancy | Status |")
    lines.append("| --- | --- | --- | --- | --- |")
    for index, case in enumerate(cases, start=1):
        lines.append(
            f"| {index} | {_md_escape(case['question'])} | "
            f"{_fmt(case['faithfulness'])} | {_fmt(case['answer_relevancy'])} | "
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
        "- RAGAS evaluation consumes Groq free-tier quota; "
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


def run(limit: int | None = None) -> dict[str, Any]:
    _ensure_project_on_path()

    from app.config import settings

    if not settings.groq_api_key.strip():
        raise EvalError(
            "GROQ_API_KEY is missing or empty. Set GROQ_API_KEY in your "
            "environment or in .env (see .env.example), then re-run."
        )

    questions = _load_questions(limit)
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
    # Opt out of RAGAS telemetry before ragas is imported.
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    _score_rows(ok_rows)

    cases = _build_cases(rows)
    aggregate = _aggregate(cases)
    failure_cases = [case for case in cases if _is_failure(case)]

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_report(
        cases=cases,
        aggregate=aggregate,
        generated_at=generated_at,
        total_count=len(questions),
        limit=limit,
    )
    _write_scores(cases, aggregate, generated_at, len(questions), limit)

    return {
        "generated_at": generated_at,
        "cases_total": len(questions),
        "aggregate": aggregate,
        "failure_count": len(failure_cases),
        "report": str(REPORT_FILE),
        "scores": str(SCORES_FILE),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run_eval",
        description="Run the RAGAS evaluation harness for SchemeGPT "
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
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    try:
        summary = run(limit=args.limit)
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
        f"Evaluation complete: {summary['cases_total']} case(s), "
        f"{summary['failure_count']} failure case(s)."
    )
    print(f"Report: {summary['report']}")
    print(f"Scores: {summary['scores']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
