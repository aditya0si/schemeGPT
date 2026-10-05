"""Offline generation metrics over the archived capture (pure, no DB/LLM)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from eval.offline_generation import (
    REQUIRED_RECORD_KEYS,
    citation_metrics,
    evaluate,
    gate_failures,
    load_fixture,
    quote_metrics,
    run,
)

ROOT = Path(__file__).resolve().parent.parent

SOURCE = {
    "source": "schemes/pm-kisan.md",
    "data_status": "sample_verified",
    "content": (
        "PM-KISAN provides income support of Rs 6,000 per year to eligible "
        "landholding farmer families in India, paid directly into their bank "
        "accounts through Direct Benefit Transfer (DBT)."
    ),
}


def test_exact_substring_quote_verifies():
    answer = (
        "PM-KISAN pays farmers.\n"
        "> PM-KISAN provides income support of Rs 6,000 per year to eligible "
        "landholding farmer families in India, paid directly into their bank "
        "accounts through Direct Benefit Transfer (DBT). "
        "[schemes/pm-kisan.md, sample_verified]\n"
    )
    metrics = quote_metrics(answer, [SOURCE])
    assert metrics["quotes"] == 1
    assert metrics["verified_quotes"] == 1
    assert metrics["verification_rate"] == 1.0


def test_quote_not_in_sources_scores_below_one():
    answer = (
        "> The government grants every citizen a free unicorn each year. "
        "[schemes/pm-kisan.md, sample_verified]\n"
    )
    metrics = quote_metrics(answer, [SOURCE])
    assert metrics["quotes"] == 1
    assert metrics["verified_quotes"] == 0
    assert metrics["verification_rate"] < 1.0


def test_no_quote_record_reports_no_rate():
    metrics = quote_metrics("A plain answer with no block quote.", [SOURCE])
    assert metrics["quotes"] == 0
    assert metrics["verified_quotes"] == 0
    assert metrics["verification_rate"] is None


def test_citation_metrics_reports_coverage_and_attribution():
    answer = (
        "> PM-KISAN provides income support of Rs 6,000 per year. "
        "[schemes/pm-kisan.md, sample_verified]\n"
    )
    metrics = citation_metrics(answer, [SOURCE])
    assert metrics["citations"] == 1
    assert metrics["attributed_citations"] == 1
    assert metrics["cited"] == 1


def test_fixture_loads_with_required_keys_and_cases():
    header, records = load_fixture()
    assert header["type"] == "header"
    assert header["captured_at"] == "2026-09-01T21:50:00+00:00"
    assert header["source_artifact"] == "eval/results/scores.json"
    assert header["cases"] == len(records)
    assert len(records) > 0
    for record in records:
        for key in REQUIRED_RECORD_KEYS:
            assert key in record, f"fixture record missing {key!r}: {record.get('id')}"
        assert isinstance(record["sources"], list)


def test_empty_fixture_is_rejected(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text('{"type": "header", "cases": 0}\n', encoding="utf-8")
    try:
        load_fixture(empty)
    except ValueError as exc:
        assert "zero cases" in str(exc)
    else:  # pragma: no cover - the guard must trip
        raise AssertionError("empty fixture was accepted")


def test_evaluate_over_committed_fixture_matches_measured_baseline():
    _, records = load_fixture()
    summary = evaluate(records)
    assert summary["cases"] == 8
    assert summary["quotes"] == 2
    assert summary["verified_quotes"] == 1
    assert summary["quote_verification_rate"] == 0.5
    assert summary["cases_with_citations"] == 2
    assert summary["citation_coverage"] == 0.25


def test_gate_flags_below_floor_and_passes_at_baseline():
    below = {"cases": 1, "quote_verification_rate": 0.0, "citation_coverage": 0.0}
    assert gate_failures(below) != []
    baseline = {
        "cases": 1,
        "quote_verification_rate": 0.5,
        "citation_coverage": 0.25,
    }
    assert gate_failures(baseline) == []


def test_output_paths_resolved_at_call_time(tmp_path, monkeypatch):
    import eval.offline_generation as offline_generation

    output = tmp_path / "scores.json"
    monkeypatch.setattr(offline_generation, "RESULTS_FILE", output)

    summary, failures = run(output=None)

    assert output.is_file(), "run() must read RESULTS_FILE at call time"
    assert failures == []
    assert summary["cases"] == 8


def test_module_import_builds_no_network_client_or_rag():
    code = (
        "import socket\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network client constructed on import')\n"
        "socket.socket = _blocked\n"
        "import eval.offline_generation\n"
        "import sys\n"
        "assert 'app.rag' not in sys.modules\n"
        "assert 'app.db' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
