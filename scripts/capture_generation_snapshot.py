"""Capture a generation snapshot fixture for the offline generation evaluation.

The fixture (``eval/fixtures/generation_snapshot.jsonl``) holds one line per
archived or freshly generated case: the question, the generated answer, and the
retrieved sources (with their chunk text). It is the frozen input the offline
metric module (``eval/offline_generation.py``) scores with no key and no
network.

Two explicit modes:

* ``--from-archive PATH`` -- offline. Read an archived live-run artifact
  (``eval/results/scores.json``), join each case to ``eval/questions.json`` by
  exact question text for its id, and write the fixture. No API key, no
  database, no network. This is the mode that produced the committed fixture.

* ``--live`` -- run the production pipeline (``app.rag.answer``) over
  ``eval/questions.json`` and record the generated answers and retrieved
  sources. This mode REQUIRES a valid ``GROQ_API_KEY`` and a running, ingested
  database; it is kept for when a credential exists and is never exercised by
  CI. Calls are paced so the free-tier token quota is not burst.

Both modes refuse to write a fixture with zero cases. The archive mode is
deterministic and byte-stable; it never rewrites, pads, or synthesises a case
that was not in the archive.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QUESTIONS_FILE = ROOT / "eval" / "questions.json"
DEFAULT_ARCHIVE = ROOT / "eval" / "results" / "scores.json"
DEFAULT_OUTPUT = ROOT / "eval" / "fixtures" / "generation_snapshot.jsonl"

# Free-tier pacing for live capture: the answer pipeline is a few thousand
# tokens per case against a shared per-minute quota, so keep one call per gap.
LIVE_INTER_CASE_SLEEP_SECONDS = 40.0

REQUIRED_RECORD_KEYS = ("id", "question", "answer", "sources")


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", str(text).casefold()).strip("-")[:48] or "case"


def _load_questions() -> list[dict]:
    if not QUESTIONS_FILE.is_file():
        return []
    return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))


def _normalize_sources(sources, contexts) -> list[dict]:
    """Return sources carrying chunk text, pairing ``sources[i]``/``contexts[i]``.

    The archived artifact already stores ``content`` on each source; when a
    source lacks it (or a caller supplies only contexts) the parallel context
    string is attached so ``app.quotes.verify_quotes`` can still do exact
    substring matching without the database.
    """
    normalized: list[dict] = []
    for index, raw in enumerate(sources or []):
        src = dict(raw) if isinstance(raw, dict) else {}
        if not src.get("content"):
            context = contexts[index] if contexts and index < len(contexts) else ""
            if context:
                src["content"] = context
        normalized.append(src)
    return normalized


def _archive_records(archive: Path) -> tuple[dict, list[dict]]:
    data = json.loads(archive.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    by_question = {
        question.get("question"): question for question in _load_questions()
    }
    records: list[dict] = []
    for index, case in enumerate(cases):
        question = case.get("question", "")
        match = by_question.get(question) or {}
        case_id = match.get("id") or f"captured-{index:02d}-{_slug(question)}"
        records.append(
            {
                "id": case_id,
                "question": question,
                "answer": case.get("answer", ""),
                "sources": _normalize_sources(
                    case.get("sources"), case.get("contexts")
                ),
            }
        )
    header = {
        "type": "header",
        "captured_at": data.get("generated_at"),
        "source_artifact": archive.as_posix(),
        "cases": len(records),
        "model": "unknown",
        "corpus_generation": "unknown",
    }
    return header, records


def _live_records(limit: int | None, sleep: float) -> tuple[dict, list[dict]]:
    # Import inside the live branch so the offline mode (and `--help`) never
    # pulls the retriever, database, or provider client into the process.
    from app.config import settings
    from app.rag import answer

    questions = _load_questions()
    if limit is not None:
        questions = questions[:limit]
    records: list[dict] = []
    for index, question in enumerate(questions, start=1):
        if index > 1 and sleep:
            time.sleep(sleep)
        payload = answer(
            question["question"],
            language=question.get("language", "en"),
            profile=question.get("profile"),
        )
        records.append(
            {
                "id": question.get("id") or f"case-{index}",
                "question": question["question"],
                "answer": payload.get("answer", ""),
                "sources": _normalize_sources(payload.get("sources"), None),
            }
        )
    header = {
        "type": "header",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": "live",
        "cases": len(records),
        "model": getattr(settings, "groq_model", "unknown") or "unknown",
        "corpus_generation": "unknown",
    }
    return header, records


def write_fixture(header: dict, records: list[dict], output: Path) -> int:
    """Write the JSONL fixture, refusing to write an empty one."""
    if not records:
        raise ValueError(
            "refusing to write a fixture with zero cases; the capture produced "
            "no records"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    lines += [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--from-archive",
        type=Path,
        metavar="PATH",
        help="offline: read an archived live-run scores.json (no key, no network)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="live: run app.rag.answer over eval/questions.json "
        "(requires a valid GROQ_API_KEY and an ingested database)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit", type=int, default=None, help="live only: cap the case count"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=LIVE_INTER_CASE_SLEEP_SECONDS,
        help="live only: seconds to wait between provider calls",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    if args.live:
        header, records = _live_records(args.limit, args.sleep)
    else:
        archive = args.from_archive
        if not archive.is_file():
            print(f"archive not found: {archive}", file=sys.stderr)
            return 1
        header, records = _archive_records(archive)

    try:
        count = write_fixture(header, records, args.output)
    except ValueError as exc:
        print(f"CAPTURE FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {count} case(s) to {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
