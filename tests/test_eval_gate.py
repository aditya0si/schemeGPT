"""Regression-gate floor logic for the RAGAS harness (pure, no RAGAS needed)."""

from eval.run_eval import GATE_FLOORS, check_gate


def test_gate_floors_are_defined():
    assert set(GATE_FLOORS) == {"faithfulness", "answer_relevancy"}
    assert all(v > 0 for v in GATE_FLOORS.values())


def test_gate_passes_when_all_above_floor():
    agg = {"faithfulness": 0.95, "answer_relevancy": 0.80}
    assert check_gate(agg) == []


def test_gate_flags_only_the_offending_metric():
    agg = {"faithfulness": 0.90, "answer_relevancy": 0.60}
    failures = check_gate(agg)
    assert len(failures) == 1
    assert "answer_relevancy" in failures[0]
    assert "faithfulness" not in failures[0]


def test_gate_flags_metric_at_exact_boundary_below():
    agg = {"faithfulness": GATE_FLOORS["faithfulness"] - 0.001, "answer_relevancy": 1.0}
    assert check_gate(agg)


def test_gate_flags_missing_metric():
    agg = {"faithfulness": 0.95}  # answer_relevancy missing
    assert check_gate(agg)


def test_build_cases_carries_all_metrics():
    """Regression: _aggregate iterates every METRICS name, so each case must
    carry all four keys (previously raised KeyError: 'context_precision')."""
    from eval.run_eval import METRICS, _build_cases

    rows = [
        {
            "question": "q",
            "answer": "a",
            "contexts": ["c"],
            "reference": "r",
            "metrics": {"faithfulness": 1.0, "answer_relevancy": 0.9,
                        "context_precision": 0.8, "context_recall": 0.7},
            "error": None,
        }
    ]
    case = _build_cases(rows)[0]
    for name in METRICS:
        assert name in case


def test_aggregate_handles_all_metric_names():
    from eval.run_eval import METRICS, _aggregate, _build_cases

    cases = _build_cases(
        [
            {
                "question": "q",
                "answer": "a",
                "contexts": [],
                "reference": "",
                "metrics": {name: 1.0 for name in METRICS},
                "error": None,
            }
        ]
    )
    agg = _aggregate(cases)
    assert all(agg[name] == 1.0 for name in METRICS)
