"""Synthetic PII corpus and benchmark tests: pure, offline, keyless.

These pin the corpus provenance (seed, counts, negatives), prove the labels are
constructed independently of the recognizers, and freeze the first measured
benchmark so the published number cannot drift without the evidence document.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.guardrails import is_aadhaar, recognize_pan
from eval.pii_benchmark import (
    MIN_NEGATIVE_RECORDS,
    evaluate,
    gate_failures,
    load_corpus,
    run,
)
from scripts.generate_synthetic_pii_corpus import SEED, build_corpus

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DOC = ROOT / "docs" / "evidence" / "PII-BENCHMARK.md"
PROVENANCE_RE = re.compile(
    r"<!--\s*pii-provenance:(?P<body>.*?)-->", re.DOTALL
)

EXPECTED_COUNTS = {
    "aadhaar": 5,
    "devanagari_digits": 3,
    "gstin": 3,
    "ifsc": 2,
    "mobile": 6,
    "pan": 3,
    "upi": 3,
}


def _documented_provenance() -> dict[str, int]:
    match = PROVENANCE_RE.search(EVIDENCE_DOC.read_text(encoding="utf-8"))
    assert match, (
        "PII-BENCHMARK.md has no `<!-- pii-provenance: ... -->` block; the "
        "evidence document must state the corpus provenance"
    )
    return {
        key: int(value)
        for key, value in re.findall(r"([a-z_]+)\s*=\s*(\d+)", match.group("body"))
    }


def test_corpus_generator_is_deterministic():
    first_header, first = build_corpus(SEED)
    second_header, second = build_corpus(SEED)
    assert first == second
    assert first_header == second_header


def test_committed_corpus_matches_a_fresh_generation():
    header, records = load_corpus()
    fresh_header, fresh = build_corpus(header["seed"])
    assert records == fresh
    assert header["counts"] == fresh_header["counts"]


def test_header_declares_synthetic_and_provenance():
    header, records = load_corpus()
    assert header["type"] == "header"
    assert header["synthetic"] is True
    assert header["seed"] == SEED
    assert "no real" in header["statement"].lower()
    assert header["records"] == len(records)
    assert header["labelled_spans"] == sum(len(r["labels"]) for r in records)
    assert header["counts"] == EXPECTED_COUNTS


def test_negatives_are_present_and_unlabelled():
    _, records = load_corpus()
    negatives = [record for record in records if not record["labels"]]
    assert len(negatives) >= MIN_NEGATIVE_RECORDS
    # The required near-miss categories are represented by id.
    ids = {record["id"] for record in negatives}
    assert "neg-aadhaar-verhoeff" in ids
    assert "neg-pan-malformed" in ids
    assert "neg-non-mobile-zero" in ids
    assert "neg-non-mobile-five" in ids
    assert "neg-high-entropy" in ids


def test_positive_aadhaar_labels_carry_a_valid_checksum():
    # The label claims a valid identifier, and an independent validator agrees.
    _, records = load_corpus()
    aadhaars = [
        label["text"]
        for record in records
        for label in record["labels"]
        if label["kind"] == "aadhaar"
    ]
    assert aadhaars
    for value in aadhaars:
        assert is_aadhaar(value), value


def test_labels_are_constructed_not_discovered():
    # The generator module must not import the recognizers at all: labels come
    # from concatenation, so the benchmark cannot be circular.
    source = (
        ROOT / "scripts" / "generate_synthetic_pii_corpus.py"
    ).read_text(encoding="utf-8")
    assert "app.guardrails" not in source
    assert "find_all" not in source
    # A malformed PAN in a negative record must not match the PAN recognizer.
    _, records = load_corpus()
    assert recognize_pan("ABCD1234F") == []
    neg = next(r for r in records if r["id"] == "neg-pan-malformed")
    assert recognize_pan(neg["text"]) == []


def test_evaluate_over_committed_corpus_matches_measured_baseline():
    _, records = load_corpus()
    summary = evaluate(records)
    assert summary["totals"] == {
        "records": 30,
        "labelled_spans": 25,
        "predictions": 25,
        "true_positives": 25,
        "false_positives": 0,
        "false_negatives": 0,
    }
    assert summary["micro"] == {"recall": 1.0, "precision": 1.0}
    assert summary["macro"] == {"recall": 1.0, "precision": 1.0}
    assert summary["negative_records_with_matches"] == 0
    for kind, count in EXPECTED_COUNTS.items():
        assert summary["per_kind"][kind]["labels"] == count
        assert summary["per_kind"][kind]["recall"] == 1.0
        assert summary["per_kind"][kind]["precision"] == 1.0


def test_evidence_document_matches_corpus_provenance():
    header, records = load_corpus()
    documented = _documented_provenance()
    assert documented["seed"] == header["seed"]
    assert documented["records"] == header["records"]
    assert documented["labelled_spans"] == header["labelled_spans"]
    assert documented["negative_records"] == header["negative_records"]
    assert documented["records"] == len(records)


def test_gate_flags_floor_breach_and_passes_at_baseline():
    below = {
        "totals": {"records": 30, "labelled_spans": 25},
        "negative_records": 8,
        "micro": {"recall": 0.5, "precision": 0.5},
        "macro": {"recall": 0.5, "precision": 0.5},
    }
    assert gate_failures(below) != []
    baseline = {
        "totals": {"records": 30, "labelled_spans": 25},
        "negative_records": 8,
        "micro": {"recall": 1.0, "precision": 1.0},
        "macro": {"recall": 1.0, "precision": 1.0},
    }
    assert gate_failures(baseline) == []


def test_gate_requires_meaningful_negatives():
    summary = {
        "totals": {"records": 30, "labelled_spans": 25},
        "negative_records": 0,
        "micro": {"recall": 1.0, "precision": 1.0},
        "macro": {"recall": 1.0, "precision": 1.0},
    }
    failures = gate_failures(summary)
    assert any("negatives" in failure for failure in failures)


def test_empty_corpus_is_rejected(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text('{"type": "header", "records": 0}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="zero records"):
        load_corpus(empty)


def test_output_path_resolved_at_call_time(tmp_path, monkeypatch):
    import eval.pii_benchmark as benchmark

    output = tmp_path / "pii.json"
    monkeypatch.setattr(benchmark, "RESULTS_FILE", output)

    summary, failures = run(output=None)

    assert output.is_file(), "run() must read RESULTS_FILE at call time"
    assert failures == []
    assert summary["micro"]["recall"] == 1.0
    on_disk = json.loads(output.read_text(encoding="utf-8"))
    assert on_disk["provenance"]["seed"] == SEED


def test_benchmark_module_imports_no_network_or_database():
    code = (
        "import socket\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network client constructed on import')\n"
        "socket.socket = _blocked\n"
        "import eval.pii_benchmark\n"
        "import sys\n"
        "assert 'app.db' not in sys.modules\n"
        "assert 'app.rag' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
