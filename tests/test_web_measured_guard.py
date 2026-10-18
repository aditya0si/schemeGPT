"""Guard the frontend's published numbers against the committed evidence.

``web/lib/measured.ts`` is the single source for every figure the offline
panel shows. This module parses that TypeScript file and re-derives each
published value from the evidence document that backs it. If the two ever
disagree -- because a number was edited in the UI without re-measuring, or
because a document was edited without updating the UI -- the test fails.

It also reconciles the **two** published MRR@4 values for one gate: 0.796875
(fp32/PyTorch run) and 0.802083 (int8 ONNX, hosted image). Both are honest for
their runtime, both are above the unchanged floor, and neither may be published
without its runtime label -- so this module parses the reconciled table in
``docs/evidence/RETRIEVAL-GATE.md`` and scans the repository for an unlabelled
duplicate of either literal.

This follows the same philosophy as ``tests/test_evidence_guards.py``: a
published claim must be checkable, and silence is not allowed to hide a
divergence.
"""

from __future__ import annotations

import os
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


# --- The two published MRR@4 values, reconciled -----------------------------
#
# One gate, two runtimes. The reconciled table in docs/evidence/RETRIEVAL-GATE.md
# is the single record of both; measured.ts must carry both values *and* both
# runtime labels, and no tracked document may publish either literal without
# naming its runtime in the same file.

_RUNTIME_ROW_RE = re.compile(
    r"^\|\s*`(?P<runtime>[^`]+)`\s*\|[^|]*\|[^|]*\|[^|]*\|"
    r"\s*(?P<hit>[0-9.]+)\s*\|\s*(?P<mrr>[0-9.]+)\s*\|",
    re.MULTILINE,
)

FP32_RUNTIME = "fp32 PyTorch (local)"
INT8_RUNTIME = "int8 ONNX (hosted image)"

# literal -> tokens, any one of which names the runtime that produced it
_RUNTIME_LABELLED_LITERALS: dict[str, tuple[str, ...]] = {
    "0.796875": ("fp32", "pytorch"),
    "0.802083": ("int8", "onnx"),
}

_SCAN_SUFFIXES = (".md", ".ts", ".tsx")
_SCAN_SKIP_DIRS = frozenset(
    {".git", "node_modules", "var", ".hermes", ".next", "__pycache__", ".venv"}
)
_SCAN_SKIP_PREFIXES = ("eval/results/", "docs/superpowers/")


def _runtime_rows() -> dict[str, tuple[str, str]]:
    """Parse the reconciled table: ``{runtime label: (hit@4, mrr@4)}``."""
    rows = {
        match.group("runtime"): (match.group("hit"), match.group("mrr"))
        for match in _RUNTIME_ROW_RE.finditer(_doc_text("docs/evidence/RETRIEVAL-GATE.md"))
    }
    assert set(rows) == {FP32_RUNTIME, INT8_RUNTIME}, (
        "docs/evidence/RETRIEVAL-GATE.md must reconcile exactly two runtimes "
        f"({FP32_RUNTIME!r}, {INT8_RUNTIME!r}) in one labelled table; found {sorted(rows)}. "
        "If a runtime was genuinely added or removed, change this test deliberately."
    )
    return rows


def test_reconciled_table_matches_the_measured_module():
    rows = _runtime_rows()
    assert MEASURED["RETRIEVAL.hitAt4"] == rows[FP32_RUNTIME][0]
    assert MEASURED["RETRIEVAL.mrrAt4"] == rows[FP32_RUNTIME][1]
    assert MEASURED["RETRIEVAL.mrrAt4Int8"] == rows[INT8_RUNTIME][1]
    assert MEASURED["RETRIEVAL.mrrAt4Runtime"] == FP32_RUNTIME, (
        "the runtime label in the UI must be the same string as the label in the "
        "reconciled table, so a reader can match a number to its runtime"
    )
    assert MEASURED["RETRIEVAL.mrrAt4Int8Runtime"] == INT8_RUNTIME


def test_no_published_gate_number_without_its_runtime():
    """A gate number that names no runtime is an unfinished citation."""
    offenders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix not in _SCAN_SUFFIXES:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(_SCAN_SKIP_PREFIXES):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            for literal, tokens in _RUNTIME_LABELLED_LITERALS.items():
                if literal in text and not any(token in lowered for token in tokens):
                    offenders.append(
                        f"{rel} publishes {literal} without naming its runtime "
                        f"({'/'.join(tokens)})"
                    )
    assert offenders == [], (
        "published MRR@4 values must name the runtime that produced them:\n  "
        + "\n  ".join(offenders)
    )
