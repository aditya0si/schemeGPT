"""Guard the frontend's published numbers against the committed evidence.

``web/lib/measured.ts`` is the single source for every figure the offline
panel shows. This module parses that TypeScript file and re-derives each
published value from the evidence document that backs it. If the two ever
disagree -- because a number was edited in the UI without re-measuring, or
because a document was edited without updating the UI -- the test fails.

This follows the same philosophy as ``tests/test_evidence_guards.py``: a
published claim must be checkable, and silence is not allowed to hide a
divergence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MEASURED_TS = ROOT / "web" / "lib" / "measured.ts"

_BLOCK_RE = re.compile(r"export const ([A-Z_]+) = \{(?P<body>.*?)\} as const;", re.DOTALL)
_ENTRY_RE = re.compile(r"(\w+)\s*:\s*(?:\"([^\"]*)\"|(\d+))")


def _parse_measured(text: str) -> dict[str, str]:
    """Return ``{"BLOCK.key": "value"}`` for every literal in the TS module."""
    parsed: dict[str, str] = {}
    for block in _BLOCK_RE.finditer(text):
        name = block.group(1)
        for entry in _ENTRY_RE.finditer(block.group("body")):
            value = entry.group(2) if entry.group(2) is not None else entry.group(3)
            parsed[f"{name}.{entry.group(1)}"] = value
    return parsed


def _doc_text(relpath: str) -> str:
    text = (ROOT / relpath).read_text(encoding="utf-8")
    assert text, f"{relpath} is empty"
    return text


# (measured.ts key, evidence document, pattern whose first group is the truth)
CHECKS: list[tuple[str, str, str]] = [
    # Retrieval gate -- docs/evidence/RETRIEVAL-GATE.md
    ("RETRIEVAL.casesCompleted", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*Cases completed\s*\|\s*([0-9/]+)"),
    ("RETRIEVAL.hitAt4", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*Hit@4\s*\|\s*([0-9.]+)"),
    ("RETRIEVAL.mrrAt4", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*MRR@4\s*\|\s*([0-9.]+)"),
    ("RETRIEVAL.hitAt4Floor", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*Hit@4 floor\s*\|\s*([0-9.]+)"),
    ("RETRIEVAL.mrrAt4Floor", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*MRR@4 floor\s*\|\s*([0-9.]+)"),
    ("CORPUS.vectors", "docs/evidence/RETRIEVAL-GATE.md", r"\|\s*Chunk count\s*\|\s*([0-9,]+)"),
    # Temporal (as-of) gate -- docs/evidence/TEMPORAL-GATE.md
    ("TEMPORAL.cases", "docs/evidence/TEMPORAL-GATE.md", r"golden set is \*\*(\d+) cases"),
    ("TEMPORAL.ladders", "docs/evidence/TEMPORAL-GATE.md", r"derived from (\d+) ladders"),
    ("TEMPORAL.asOf", "docs/evidence/TEMPORAL-GATE.md", r"\|\s*`as_of_accuracy`\s*\|\s*([0-9.]+)"),
    ("TEMPORAL.boundary", "docs/evidence/TEMPORAL-GATE.md", r"\|\s*`boundary_accuracy`\s*\|\s*([0-9.]+)"),
    ("TEMPORAL.supersession", "docs/evidence/TEMPORAL-GATE.md", r"\|\s*`supersession_accuracy`\s*\|\s*([0-9.]+)"),
    ("TEMPORAL.refusal", "docs/evidence/TEMPORAL-GATE.md", r"\|\s*`refusal_accuracy`\s*\|\s*([0-9.]+)"),
    ("TEMPORAL.eraMixing", "docs/evidence/TEMPORAL-GATE.md", r"\|\s*`era_mixing_rate`\s*\|\s*([0-9.]+)"),
    ("CORPUS.documents", "docs/evidence/TEMPORAL-GATE.md", r"over ([0-9,]+) documents"),
    ("CORPUS.documentsDeclaringADate", "docs/evidence/TEMPORAL-GATE.md", r"only \*\*(\d+) declare"),
    # PII benchmark -- docs/evidence/PII-BENCHMARK.md
    ("PII.microRecall", "docs/evidence/PII-BENCHMARK.md", r"micro recall=([0-9.]+)"),
    ("PII.microPrecision", "docs/evidence/PII-BENCHMARK.md", r"micro recall=[0-9.]+ precision=([0-9.]+)"),
    # Jurisdictions -- docs/data-operations.md
    ("CORPUS.jurisdictions", "docs/data-operations.md", r"(\d+) jurisdictions"),
]


MEASURED = _parse_measured(MEASURED_TS.read_text(encoding="utf-8"))


def test_measured_module_declares_every_guarded_key():
    missing = [key for key, _, _ in CHECKS if key not in MEASURED]
    assert missing == [], (
        f"web/lib/measured.ts no longer declares {missing}; the offline panel "
        f"and this guard must agree on the published keys"
    )


@pytest.mark.parametrize("key,doc,pattern", CHECKS, ids=[c[0] for c in CHECKS])
def test_measured_ts_matches_evidence_doc(key, doc, pattern):
    frontend_value = MEASURED[key]
    match = re.search(pattern, _doc_text(doc))
    assert match, f"could not find {key} in {doc} with {pattern!r}"
    doc_value = match.group(1)
    assert frontend_value == doc_value, (
        f"{key} disagrees with {doc}: frontend says {frontend_value!r}, evidence "
        f"says {doc_value!r}. Re-measure, then update the document and the UI "
        f"together; never edit one side to silence this guard."
    )
