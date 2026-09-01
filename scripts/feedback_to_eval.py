"""Turn curated thumbs-up feedback into candidate eval cases.

Reads ``data/feedback.jsonl`` (appended by POST /feedback), keeps ratings the
curator marked as accepted via ``--from-file`` review, deduplicates by
question, and writes/merges ``eval/candidate_questions.json``.

Workflow (the human is the gate — nothing here auto-promotes):
    1. Review data/feedback.jsonl and delete/keep lines (thumbs-up only are
       considered; edit the reference answers as needed).
    2. python scripts/feedback_to_eval.py
    3. Review eval/candidate_questions.json, then copy the good cases into
       eval/questions.json and re-run the eval to measure the new baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK_FILE = ROOT / "data" / "feedback.jsonl"
OUT_FILE = ROOT / "eval" / "candidate_questions.json"
EXISTING = ROOT / "eval" / "questions.json"


def _question_id(question: str) -> str:
    return hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rating", default="up", choices=("up", "down"),
        help="which ratings become candidates (default: up)",
    )
    args = parser.parse_args(argv)

    if not FEEDBACK_FILE.is_file():
        print(f"no feedback file at {FEEDBACK_FILE}")
        return 0

    existing_questions = set()
    if EXISTING.is_file():
        for case in json.loads(EXISTING.read_text(encoding="utf-8")):
            existing_questions.add(_question_id(case.get("question", "")))

    candidates = []
    if OUT_FILE.is_file():
        candidates = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    seen = {_question_id(c.get("question", "")) for c in candidates}

    added = skipped_known = skipped_dup = 0
    for line in FEEDBACK_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("rating") != args.rating:
            continue
        question = (record.get("question") or "").strip()
        answer = (record.get("answer") or "").strip()
        if len(question) < 2 or len(answer) < 1:
            continue
        qid = _question_id(question)
        if qid in existing_questions:
            skipped_known += 1
            continue
        if qid in seen:
            skipped_dup += 1
            continue
        seen.add(qid)
        candidates.append(
            {
                "question": question,
                "reference": answer,
                "language": record.get("language", "en"),
                "origin": "feedback",
                "ts": record.get("ts"),
            }
        )
        added += 1

    OUT_FILE.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{added} candidate(s) added, {skipped_known} already in questions.json, "
        f"{skipped_dup} duplicates skipped -> {OUT_FILE}"
    )
    print("Review the file, then copy curated cases into eval/questions.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
