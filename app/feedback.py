"""Feedback loop: citizen ratings -> growing eval set.

``record_feedback`` appends one JSON line per rating to ``data/feedback.jsonl``
(git-ignored user data, never question profiles). ``scripts/feedback_to_eval.py``
later turns curated thumbs-up cases into candidate eval questions, so real
usage grows the regression suite. Metrics count ratings for /metrics.

The file is appended under a lock and every write is bounded by the schema
limits (question 2,000 / answer 8,000 / comment 500 chars) — a hostile client
cannot grow the file faster than an honest one.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import ROOT_DIR
from app.metrics import inc

logger = logging.getLogger(__name__)

FEEDBACK_FILE = ROOT_DIR / "data" / "feedback.jsonl"
_write_lock = threading.Lock()


def record_feedback(
    question: str,
    answer: str,
    rating: str,
    language: str = "en",
    comment: str | None = None,
) -> bool:
    """Append one rating; returns False (and logs) when storage fails."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "answer": answer,
        "rating": rating,
        "language": language,
        "comment": comment,
    }
    try:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            with FEEDBACK_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("Could not persist feedback record.", exc_info=True)
        return False
    inc("feedback_up" if rating == "up" else "feedback_down")
    return True
