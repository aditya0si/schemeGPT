"""Unit tests for the feedback loop (endpoint + eval-set growth)."""

import json

import pytest
from fastapi.testclient import TestClient

from app import feedback


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """TestClient with feedback storage pointed at a temp file and a stubbed
    live pipeline (no DB, no Groq)."""
    import app.main as main_mod

    monkeypatch.setattr(feedback, "FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    return TestClient(main_mod.app)


def test_record_feedback_appends_and_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(feedback, "FEEDBACK_FILE", tmp_path / "fb.jsonl")
    assert feedback.record_feedback("q?", "a", "up") is True
    assert feedback.record_feedback("q2?", "a2", "down") is True
    lines = [json.loads(l) for l in (tmp_path / "fb.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["rating"] == "up"
    assert lines[1]["rating"] == "down"
    assert "ts" in lines[0]


def test_record_feedback_survives_io_error(monkeypatch, tmp_path):
    monkeypatch.setattr(feedback, "FEEDBACK_FILE", tmp_path / "no-dir" / "sub" / "fb.jsonl")
    # parents are created; force failure by making the parent a file instead
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(feedback, "FEEDBACK_FILE", blocker / "fb.jsonl")
    assert feedback.record_feedback("q?", "a", "up") is False


def test_feedback_endpoint_roundtrip(client, tmp_path):
    resp = client.post(
        "/feedback",
        json={
            "question": "How much does PM-KISAN pay?",
            "answer": "Rs 6000 per year.",
            "rating": "up",
            "language": "en",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"stored": True}
    saved = json.loads((tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert saved["question"] == "How much does PM-KISAN pay?"


def test_feedback_endpoint_rejects_bad_rating(client):
    resp = client.post(
        "/feedback",
        json={"question": "q?", "answer": "a", "rating": "meh"},
    )
    assert resp.status_code == 422


def test_feedback_endpoint_rejects_oversized_answer(client):
    resp = client.post(
        "/feedback",
        json={"question": "q?", "answer": "a" * 9000, "rating": "up"},
    )
    assert resp.status_code == 422


def test_feedback_to_eval_merges_deduped(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(tmp_path))
    from scripts import feedback_to_eval  # noqa: E402

    fb = tmp_path / "fb.jsonl"
    records = [
        {"ts": "t1", "question": "Best scheme for farmers?", "answer": "PM-KISAN", "rating": "up", "language": "en"},
        {"ts": "t2", "question": "best scheme for farmers?", "answer": "PM-KISAN dup", "rating": "up", "language": "en"},
        {"ts": "t3", "question": "Bad one", "answer": "x", "rating": "down", "language": "en"},
    ]
    fb.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    monkeypatch.setattr(feedback_to_eval, "FEEDBACK_FILE", fb)
    out = tmp_path / "candidates.json"
    monkeypatch.setattr(feedback_to_eval, "OUT_FILE", out)
    monkeypatch.setattr(feedback_to_eval, "EXISTING", tmp_path / "none.json")

    assert feedback_to_eval.main([]) == 0
    candidates = json.loads(out.read_text(encoding="utf-8"))
    assert len(candidates) == 1
    assert candidates[0]["origin"] == "feedback"
