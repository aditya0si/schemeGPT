"""Regression-gate logic for the live generation judge harness."""

from eval.run_eval import GATE_FLOORS, check_gate


def test_gate_floors_are_defined():
    assert GATE_FLOORS["faithfulness"] >= 0.85
    assert GATE_FLOORS["answer_relevancy"] >= 0.70


def test_gate_passes_when_all_above_floor_and_complete():
    agg = {"faithfulness": 0.95, "answer_relevancy": 0.80}
    assert check_gate(agg, scored_count=20, expected_count=20, error_count=0) == []


def test_gate_flags_only_the_offending_metric():
    agg = {"faithfulness": 0.90, "answer_relevancy": 0.60}
    failures = check_gate(agg)
    assert len(failures) == 1
    assert "answer_relevancy" in failures[0]
    assert "faithfulness" not in failures[0]


def test_gate_flags_metric_at_exact_boundary_below():
    agg = {
        "faithfulness": GATE_FLOORS["faithfulness"] - 0.001,
        "answer_relevancy": 1.0,
    }
    assert check_gate(agg)


def test_gate_flags_missing_metric():
    agg = {"faithfulness": 0.95}
    assert check_gate(agg)


def test_gate_cannot_pass_with_one_perfect_row_and_nineteen_missing():
    agg = {"faithfulness": 1.0, "answer_relevancy": 1.0}
    failures = check_gate(
        agg,
        scored_count=1,
        expected_count=20,
        error_count=19,
    )
    assert any("coverage" in failure for failure in failures)
    assert any("errors" in failure for failure in failures)


def test_gate_rejects_inconsistent_counts_even_without_recorded_errors():
    failures = check_gate(
        {"faithfulness": 1.0, "answer_relevancy": 1.0},
        scored_count=19,
        expected_count=20,
        error_count=0,
    )
    assert any("19/20" in failure for failure in failures)


def test_build_cases_carries_all_metrics():
    """Every report case carries every metric even when the judge returns none."""
    from eval.run_eval import METRICS, _build_cases

    cases = _build_cases(
        [
            {
                "question": "q",
                "reference": "r",
                "answer": "a",
                "contexts": ["c"],
                "sources": [],
                "metrics": {name: 1.0 for name in METRICS},
                "error": None,
            }
        ]
    )
    for name in METRICS:
        assert name in cases[0]


def test_aggregate_handles_all_metric_names():
    from eval.run_eval import METRICS, _aggregate, _build_cases

    cases = _build_cases(
        [
            {
                "question": "q",
                "reference": "r",
                "answer": "a",
                "contexts": ["c"],
                "sources": [],
                "metrics": {name: 1.0 for name in METRICS},
                "error": None,
            }
        ]
    )
    agg = _aggregate(cases)
    assert all(agg[name] == 1.0 for name in METRICS)


def test_parse_judge_scores_accepts_fenced_json():
    from eval.run_eval import _parse_judge_scores

    scores = _parse_judge_scores(
        "```json\n"
        '{"faithfulness": 0.9, "answer_relevancy": 0.8, '
        '"context_precision": 0.7, "context_recall": 0.6}'
        "\n```"
    )
    assert scores == {
        "faithfulness": 0.9,
        "answer_relevancy": 0.8,
        "context_precision": 0.7,
        "context_recall": 0.6,
    }


def test_parse_judge_scores_rejects_missing_or_out_of_range_metrics():
    from eval.run_eval import _parse_judge_scores

    import pytest

    with pytest.raises(ValueError, match="missing"):
        _parse_judge_scores('{"faithfulness": 0.9}')
    with pytest.raises(ValueError, match="between 0 and 1"):
        _parse_judge_scores(
            '{"faithfulness": 1.1, "answer_relevancy": 0.8, '
            '"context_precision": 0.7, "context_recall": 0.6}'
        )
