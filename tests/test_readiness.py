"""Kubernetes/Fly-style liveness and readiness contracts."""

from fastapi.testclient import TestClient

import app.main as main
from app.config import settings

client = TestClient(main.app)


def _complete_corpus(monkeypatch, count: int = 42, generation: str = "gen-1"):
    monkeypatch.setattr(main, "count_vectors", lambda: count)
    monkeypatch.setattr(main, "stored_embedding_model", lambda: settings.embedding_model)
    monkeypatch.setattr(main, "stored_corpus_generation", lambda: generation)
    monkeypatch.setattr(main, "stored_corpus_chunk_count", lambda: count)
    monkeypatch.setattr(main, "count_generation_vectors", lambda value: count)


def test_livez_has_no_dependency_checks(monkeypatch):
    monkeypatch.setattr(main, "count_vectors", lambda: (_ for _ in ()).throw(RuntimeError()))
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readyz_reports_live_stack(monkeypatch):
    _complete_corpus(monkeypatch)
    monkeypatch.setattr(settings, "groq_api_key", "configured")
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "mode": "live",
        "checks": {
            "database": "ok",
            "vectors": 42,
            "embedding_model": "ok",
            "corpus_generation": "ok",
        },
    }


def test_readyz_fails_when_corpus_is_empty(monkeypatch):
    _complete_corpus(monkeypatch, count=0)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["vectors"] == 0


def test_readyz_fails_on_embedding_model_drift(monkeypatch):
    _complete_corpus(monkeypatch)
    monkeypatch.setattr(main, "stored_embedding_model", lambda: "old/model")
    response = client.get("/readyz")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["checks"]["embedding_model"] == "mismatch"
    assert "old/model" not in str(detail)


def test_readyz_fails_on_partial_or_mixed_corpus_generation(monkeypatch):
    _complete_corpus(monkeypatch)
    monkeypatch.setattr(main, "count_generation_vectors", lambda generation: 41)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["corpus_generation"] == "incomplete"


def test_readyz_sanitizes_database_errors(monkeypatch):
    def fail():
        raise RuntimeError("postgresql://user:secret@db/private")

    monkeypatch.setattr(main, "count_vectors", fail)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert response.json()["detail"]["checks"]["database"] == "unavailable"


def test_readyz_sanitizes_generation_count_errors(monkeypatch):
    _complete_corpus(monkeypatch)

    def fail(generation):
        raise RuntimeError("postgresql://user:secret@db/private")

    monkeypatch.setattr(main, "count_generation_vectors", fail)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert "secret" not in response.text
    assert response.json()["detail"]["checks"]["database"] == "unavailable"
