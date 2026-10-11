"""Regression-gate logic for the live generation judge harness."""

from eval.run_eval import GATE_FLOORS, check_gate


def _no_sleep(monkeypatch, run_eval):
    monkeypatch.setattr(run_eval, "INTER_CASE_SLEEP_SECONDS", 0.0)
    monkeypatch.setattr(run_eval, "RATE_LIMIT_BACKOFF_SECONDS", 0.0)


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


# --- fallback reason accuracy -------------------------------------------------
# The old message blamed the credential for every provider failure. These pin
# the three distinct conditions apart and prove a throttled provider is not
# reported as a bad key.


def test_provider_failure_reason_distinguishes_three_conditions():
    from eval.run_eval import provider_failure_reason

    missing = provider_failure_reason(configured=False)
    rejected = provider_failure_reason(
        configured=True, error_type="AuthenticationError", status_code=401
    )
    throttled = provider_failure_reason(
        configured=True, error_type="RateLimitError", status_code=429
    )
    unavailable = provider_failure_reason(
        configured=True, error_type="APIConnectionError"
    )

    assert "no credential" in missing
    assert "credential rejected" in rejected
    assert "401" in rejected
    assert "rate-limited" in throttled
    assert "429" in throttled
    assert "unavailable" in unavailable
    assert len({missing, rejected, throttled, unavailable}) == 4, (
        "each fallback cause must read as its own reason"
    )


def test_rate_limit_and_unavailable_reasons_never_blame_the_credential():
    from eval.run_eval import provider_failure_reason

    for error_type, status_code in (("RateLimitError", 429), ("APIConnectionError", None)):
        reason = provider_failure_reason(
            configured=True, error_type=error_type, status_code=status_code
        )
        assert "credential" not in reason.lower()
        assert "GROQ_API_KEY" not in reason


def test_rate_limit_fallback_message_does_not_name_the_key():
    from eval.run_eval import fallback_error_message, provider_failure_reason

    reason = provider_failure_reason(
        configured=True, error_type="RateLimitError", status_code=429
    )
    message = fallback_error_message("demo", reason)

    assert "RateLimitError" in message
    assert "429" in message
    assert "GROQ_API_KEY" not in message
    assert "credential" not in message.lower()


def test_run_pipeline_records_a_throttle_as_provider_not_credential(
    monkeypatch,
):
    import app.rag
    from app.config import settings

    import eval.run_eval as run_eval

    _no_sleep(monkeypatch, run_eval)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")

    def fake_answer(question, language="en", profile=None):
        return {
            "answer": "pre-made demo text",
            "sources": [],
            "mode": "demo",
            "provider_error_type": "RateLimitError",
            "provider_status_code": 429,
        }

    monkeypatch.setattr(app.rag, "answer", fake_answer)
    rows = run_eval._run_pipeline([{"question": "What is PM-KISAN?"}])

    error = rows[0]["error"]
    assert "RateLimitError" in error
    assert "429" in error
    assert "GROQ_API_KEY" not in error
    assert "credential" not in error.lower()


def test_run_pipeline_records_missing_credential_distinctly(monkeypatch):
    import app.rag
    from app.config import settings

    import eval.run_eval as run_eval

    _no_sleep(monkeypatch, run_eval)
    monkeypatch.setattr(settings, "groq_api_key", "")

    def fake_answer(question, language="en", profile=None):
        return {"answer": "pre-made demo text", "sources": [], "mode": "demo"}

    monkeypatch.setattr(app.rag, "answer", fake_answer)
    rows = run_eval._run_pipeline([{"question": "What is PM-KISAN?"}])

    assert "no credential" in rows[0]["error"]


def test_run_pipeline_records_rejected_credential_distinctly(monkeypatch):
    import app.rag
    from app.config import settings

    import eval.run_eval as run_eval

    _no_sleep(monkeypatch, run_eval)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-used")

    def fake_answer(question, language="en", profile=None):
        return {
            "answer": "retrieval-only text",
            "sources": [],
            "mode": "degraded",
            "provider_error_type": "AuthenticationError",
            "provider_status_code": 401,
        }

    monkeypatch.setattr(app.rag, "answer", fake_answer)
    rows = run_eval._run_pipeline([{"question": "What is PM-KISAN?"}])

    error = rows[0]["error"]
    assert "credential rejected" in error
    assert "401" in error
