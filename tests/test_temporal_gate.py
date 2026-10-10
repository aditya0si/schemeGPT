"""The temporal (as-of) gate: golden-set provenance, reproducibility, metrics.

Phase 8 / track 1, Task 3. The golden set is *derived* from the frozen dated-
claims artifact, so these tests pin three things: it is byte-for-byte
reproducible from the artifact, every expectation is traceable to a claim id,
and the gate scores the pure-function answer exactly (and fails when it does
not).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.temporal_answer import load_claims, match_scheme
from eval.temporal_gate import (
    RETRIEVAL_EXPECTED,
    evaluate,
    gate_failures,
    load_golden,
    run,
)
from scripts.generate_temporal_golden import (
    DEFAULT_OUTPUT,
    UNMATCHED_QUESTION,
    build_golden,
    load_artifact,
    serialise,
)

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_KINDS = {
    "after_last": 10,
    "before_first": 10,
    "day_before": 31,
    "effective_date": 41,
    "inside_range": 31,
    "unmatched": 1,
}


# --- golden-set provenance and reproducibility --------------------------------


def test_golden_header_counts_match_the_artifact():
    header, records = load_golden()
    artifact_header, claims = load_artifact()
    assert header["generator"] == "scripts/generate_temporal_golden.py"
    assert header["artifact"] == "eval/fixtures/temporal_claims.jsonl"
    assert header["artifact_claims"] == len(claims) == 41
    assert header["ladders"] == 10
    assert header["cases"] == len(records) == 124
    assert header["kinds"] == EXPECTED_KINDS


def test_golden_set_is_reproducible_from_the_artifact_byte_for_byte():
    committed = DEFAULT_OUTPUT.read_bytes()
    header, records = build_golden()
    assert serialise(header, records).encode("utf-8") == committed


def test_golden_check_mode_reports_current():
    result = subprocess.run(
        [sys.executable, "scripts/generate_temporal_golden.py", "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "golden set is current" in result.stdout


def test_golden_file_is_lf_and_header_first():
    raw = DEFAULT_OUTPUT.read_bytes()
    assert b"\r\n" not in raw
    first = json.loads(raw.decode("utf-8").splitlines()[0])
    assert first["type"] == "header"


def test_every_golden_expectation_is_traceable_to_the_artifact():
    _, records = load_golden()
    _, claims = load_artifact()
    by_id = {claim["claim_id"]: claim for claim in claims}
    for record in records:
        assert record["derived_from"], f"{record['id']} has no provenance"
        for claim_id in record["derived_from"]:
            assert claim_id in by_id, f"{record['id']} cites unknown {claim_id}"
        if record["expect"] == "answer":
            governing = by_id[record["governing_claim_id"]]
            assert governing["value"] == record["expected_value"]
            assert governing["effective_from"] == record["expected_effective_from"]
            assert governing["superseded_by"] == record["successor_claim_id"]
            if record["successor_claim_id"] is None:
                assert record["successor_value"] is None
                assert record["successor_effective_from"] is None
            else:
                successor = by_id[record["successor_claim_id"]]
                assert successor["value"] == record["successor_value"]
                assert successor["effective_from"] == record["successor_effective_from"]
        else:
            assert record["governing_claim_id"] is None
            assert record["expected_value"] is None


def test_every_ladder_case_question_resolves_to_its_source():
    _, records = load_golden()
    claims = load_claims()
    assert claims is not None
    for record in records:
        if record["source"] is None:
            continue
        ladder = match_scheme(record["question"], claims)
        assert ladder is not None, f"{record['id']} did not match a ladder"
        assert ladder[0].source == record["source"], record["id"]
    assert match_scheme(UNMATCHED_QUESTION, claims) is None


# --- the gate scores the pure function exactly --------------------------------


def test_gate_scores_every_consistency_metric_exactly(tmp_path):
    summary, failures = run(
        output=tmp_path / "temporal_scores.json",
        report=tmp_path / "temporal_report.md",
    )
    assert failures == []
    assert summary["as_of_accuracy"] == 1.0
    assert summary["boundary_accuracy"] == 1.0
    assert summary["supersession_accuracy"] == 1.0
    assert summary["era_mixing_rate"] == 0.0
    assert summary["refusal_accuracy"] == 1.0
    # Invariance is only measured under --check-default-mode (needs the DB).
    assert summary["invariance"] is None
    assert (tmp_path / "temporal_report.md").is_file()
    assert (tmp_path / "temporal_scores.json").is_file()


def test_gate_includes_the_artifact_missing_refusal_branch():
    _, records = load_golden()
    summary = evaluate(records)
    kinds = summary["kinds"]
    assert kinds["artifact_missing"] == 1
    assert summary["counts"]["refusal_expected"] == 12
    assert summary["refusal_accuracy"] == 1.0


def test_gate_detects_a_wrong_era_value(tmp_path):
    def wrong(question, as_of, language="en"):
        return {
            "answer": "As of x, the value in force for T is \u20b9999,999 per month.",
            "sources": [{"source": "data/myscheme/fadcs.md"}],
            "quotes": [],
            "steps": [],
            "mode": "as_of",
            "notice": "",
            "language": language,
        }

    summary, failures = run(
        output=tmp_path / "s.json",
        report=tmp_path / "r.md",
        answer_fn=wrong,
    )
    assert summary["as_of_accuracy"] == 0.0
    assert summary["era_mixing_rate"] > 0.0
    assert failures


def test_honest_refusal_is_an_as_of_miss_not_era_mixing(tmp_path):
    def refuse(question, as_of, language="en"):
        return {
            "answer": "No current or latest value has been substituted for the "
            "requested date.",
            "sources": [],
            "quotes": [],
            "steps": [],
            "mode": "as_of",
            "notice": "",
            "language": language,
        }

    summary, failures = run(
        output=tmp_path / "s.json",
        report=tmp_path / "r.md",
        answer_fn=refuse,
    )
    # It never presents a wrong-era value, so era-mixing stays zero...
    assert summary["era_mixing_rate"] == 0.0
    # ...but every answer-expected case is an as-of miss, so the gate fails.
    assert summary["as_of_accuracy"] == 0.0
    assert failures


# --- invariance (R4) ----------------------------------------------------------


def test_run_measures_invariance_when_default_mode_checked(monkeypatch, tmp_path):
    import eval.temporal_gate as temporal_gate

    monkeypatch.setattr(
        temporal_gate,
        "check_default_mode_retrieval",
        lambda: {
            "metric": 1.0,
            "passed": True,
            "expected": dict(RETRIEVAL_EXPECTED),
            "observed": dict(RETRIEVAL_EXPECTED),
            "gate_failures": [],
        },
    )
    summary, failures = run(
        output=tmp_path / "s.json",
        report=tmp_path / "r.md",
        check_default_mode=True,
    )
    assert summary["invariance"] == 1.0
    assert failures == []


def test_run_fails_when_invariance_is_breached(monkeypatch, tmp_path):
    import eval.temporal_gate as temporal_gate

    monkeypatch.setattr(
        temporal_gate,
        "check_default_mode_retrieval",
        lambda: {
            "metric": 0.0,
            "passed": False,
            "expected": dict(RETRIEVAL_EXPECTED),
            "observed": {**RETRIEVAL_EXPECTED, "hit_rate_at_k": 0.0},
            "gate_failures": ["hit_rate_at_k: 0.000 < 0.85"],
        },
    )
    summary, failures = run(
        output=tmp_path / "s.json",
        report=tmp_path / "r.md",
        check_default_mode=True,
    )
    assert summary["invariance"] == 0.0
    assert any("invariance" in failure for failure in failures)


def test_check_default_mode_handles_an_unavailable_database(monkeypatch):
    import eval.retrieval_gate as retrieval_gate
    import eval.temporal_gate as temporal_gate

    def boom(**kwargs):
        raise RuntimeError("no active corpus generation recorded")

    monkeypatch.setattr(retrieval_gate, "run", boom)
    result = temporal_gate.check_default_mode_retrieval()
    assert result["metric"] == 0.0
    assert result["passed"] is False
    assert result["observed"] is None


def test_gate_failures_rejects_missing_coverage():
    assert gate_failures({"cases": 0, "counts": {}, "as_of_accuracy": 1.0})


# --- offline / no-DB import ---------------------------------------------------


def test_gate_module_imports_without_database_or_rag():
    code = (
        "import eval.temporal_gate\n"
        "import sys\n"
        "assert 'app.db' not in sys.modules\n"
        "assert 'app.rag' not in sys.modules\n"
        "assert 'eval.retrieval_gate' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
