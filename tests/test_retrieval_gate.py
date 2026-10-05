"""Deterministic retrieval quality gate; no database or LLM required."""

from types import SimpleNamespace

import pytest

from eval.retrieval_gate import evaluate_cases, gate_failures


class FakeRetriever:
    def __init__(self, results):
        self.results = results

    def invoke(self, question):
        value = self.results[question]
        if isinstance(value, Exception):
            raise value
        return [SimpleNamespace(metadata={"source": source}) for source in value]


def test_retrieval_eval_scores_exact_source_rank_and_skips_unlabelled_cases():
    cases = [
        {"id": "one", "question": "q1", "expected_sources": ["schemes/a.md"]},
        {"id": "two", "question": "q2", "expected_sources": ["schemes/b.md"]},
        {"id": "skip", "question": "q3"},
    ]
    summary = evaluate_cases(
        cases,
        FakeRetriever({
            "q1": ["schemes/a.md", "schemes/z.md"],
            "q2": ["schemes/z.md", "schemes/b.md"],
        }),
        top_k=4,
    )
    assert summary["labelled_cases"] == 2
    assert summary["completed_cases"] == 2
    assert summary["hit_rate_at_k"] == 1.0
    assert summary["mrr_at_k"] == 0.75


def test_retrieval_eval_records_errors_without_hiding_them():
    cases = [{"id": "broken", "question": "q", "expected_sources": ["schemes/a.md"]}]
    summary = evaluate_cases(cases, FakeRetriever({"q": RuntimeError("db down")}))
    assert summary["completed_cases"] == 0
    assert summary["error_count"] == 1
    assert gate_failures(summary)


def test_gate_rejects_partial_coverage_even_with_perfect_scores():
    summary = {
        "labelled_cases": 20,
        "completed_cases": 1,
        "error_count": 19,
        "hit_rate_at_k": 1.0,
        "mrr_at_k": 1.0,
    }
    failures = gate_failures(summary)
    assert any("coverage" in failure for failure in failures)
    assert any("errors" in failure for failure in failures)


def test_gate_passes_complete_results_at_or_above_floors():
    summary = {
        "labelled_cases": 20,
        "completed_cases": 20,
        "error_count": 0,
        "hit_rate_at_k": 0.90,
        "mrr_at_k": 0.70,
    }
    assert gate_failures(summary) == []


def _labelled_cases(count: int) -> list[dict]:
    return [
        {"id": f"case-{i}", "question": f"q{i}", "expected_sources": ["schemes/a.md"]}
        for i in range(count)
    ]


def test_run_binds_production_retriever_to_recorded_generation(monkeypatch, tmp_path):
    import app.db as db
    import app.rag as rag
    from eval import retrieval_gate

    monkeypatch.setattr(db, "read_corpus_generation", lambda: "gen-77")
    seen: list[str | None] = []

    class Retriever:
        def invoke(self, question):
            return [SimpleNamespace(metadata={"source": "schemes/a.md"})]

    def fake_get_retriever(corpus_generation=None):
        seen.append(corpus_generation)
        return Retriever()

    monkeypatch.setattr(rag, "get_retriever", fake_get_retriever)
    monkeypatch.setattr(
        retrieval_gate, "_load_questions", lambda limit: _labelled_cases(16)
    )

    summary, failures = retrieval_gate.run(output=tmp_path / "scores.json")

    assert seen == ["gen-77"]
    assert summary["corpus_generation"] == "gen-77"
    assert failures == []


def test_run_refuses_unknown_generation(monkeypatch, tmp_path):
    import app.db as db
    from eval import retrieval_gate

    monkeypatch.setattr(db, "read_corpus_generation", lambda: None)

    with pytest.raises(RuntimeError, match="corpus generation"):
        retrieval_gate.run(output=tmp_path / "scores.json")


def test_gate_rejects_dataset_shrink_below_required_labelled_cases():
    summary = {
        "labelled_cases": 15,
        "completed_cases": 15,
        "error_count": 0,
        "hit_rate_at_k": 1.0,
        "mrr_at_k": 1.0,
    }

    failures = gate_failures(summary)

    assert any("required 16" in failure for failure in failures)
