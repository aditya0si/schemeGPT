"""PII integration tests for the synchronous answer path.

The load-bearing test is the egress assertion: a request carrying a synthetic,
checksum-valid Aadhaar is driven through the real ``app.rag.answer`` pipeline
with a stubbed provider client, and the exact prompt payload the client received
is asserted to contain no identifier. No network and no database are involved.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

import app.rag as rag
from app.config import settings
from app.guardrails import middleware
from app.guardrails.recognizers import find_all

# Synthetic and checksum-valid (see tests/test_guardrails_recognizers.py); not a
# real person's identifier.
AADHAAR = "234123412346"


class _RecordingProvider:
    """A stubbed provider client that records every prompt it is handed."""

    def __init__(self) -> None:
        self.prompts = []

    def __call__(self, prompt_value):
        self.prompts.append(prompt_value)
        human = prompt_value.messages[-1].content
        return f"> Policy fact. [schemes/pm-kisan.md, sample_verified]\n{human}"

    def payload_text(self) -> str:
        return "\n".join(
            message.content
            for prompt in self.prompts
            for message in prompt.messages
        )


def _configure(monkeypatch, provider: _RecordingProvider) -> None:
    """Stub the provider boundary and everything the DB would provide."""
    source = Document(
        page_content="PM-KISAN gives income support to eligible farmer families.",
        metadata={"source": "schemes/pm-kisan.md", "data_status": "sample_verified"},
    )
    monkeypatch.setattr(settings, "groq_api_key", "configured")
    monkeypatch.setattr(settings, "enable_pii_vault", True)
    monkeypatch.setattr(rag.semantic_cache, "capture_generation", lambda: "gen-1")
    monkeypatch.setattr(rag.semantic_cache, "lookup", lambda *a, **k: None)
    monkeypatch.setattr(rag.semantic_cache, "store", lambda *a, **k: None)
    monkeypatch.setattr(rag, "retrieve_context", lambda *a, **k: ([source], []))
    monkeypatch.setattr(rag, "get_llm", lambda *a, **k: RunnableLambda(provider))
    operator = MagicMock()
    operator.gate.return_value = "ok"
    monkeypatch.setattr(rag, "operator", operator)


def test_egress_payload_contains_no_identifier(monkeypatch):
    """The provider client never receives the Aadhaar, only a placeholder."""
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    question = f"My Aadhaar number is {AADHAAR}, which schemes can I get?"

    result = middleware.answer_with_pii_protection(question)

    assert provider.prompts, "the provider client must have been called"
    payload = provider.payload_text()
    # The exact payload the stubbed client received:
    assert AADHAAR not in payload
    assert "2341 2341 2346" not in payload
    assert find_all(payload) == [], "no identifier-shaped string may egress"
    # What did egress is the placeholder, not the value.
    assert "[[PII:" in payload
    # And the answer the citizen sees has the real value put back.
    assert AADHAAR in result["answer"]


def test_pii_request_bypasses_both_cache_lookup_and_store(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    lookups = MagicMock(return_value=None)
    stores = MagicMock()
    monkeypatch.setattr(rag.semantic_cache, "lookup", lookups)
    monkeypatch.setattr(rag.semantic_cache, "store", stores)

    result = middleware.answer_with_pii_protection(f"my aadhaar {AADHAAR}")

    assert AADHAAR in result["answer"]
    lookups.assert_not_called()
    stores.assert_not_called()


def test_cache_safety_second_request_cannot_receive_first_pii(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    cache: dict = {}

    def fake_store(question, language, profile_h, payload, generation):
        cache[(question, language, profile_h)] = payload

    def fake_lookup(question, language, profile_h, generation):
        return cache.get((question, language, profile_h))

    monkeypatch.setattr(rag.semantic_cache, "store", fake_store)
    monkeypatch.setattr(rag.semantic_cache, "lookup", fake_lookup)

    first = middleware.answer_with_pii_protection(f"my aadhaar {AADHAAR}")
    assert AADHAAR in first["answer"]
    assert cache == {}, "an answer containing restored PII must never be cached"

    # A second, different request cannot be served the first person's identifier.
    second = middleware.answer_with_pii_protection("What is PM-KISAN?")
    assert AADHAAR not in second["answer"]
    assert find_all(second["answer"]) == []


def test_clean_question_still_uses_the_semantic_cache(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    lookups = MagicMock(return_value=None)
    stores = MagicMock()
    monkeypatch.setattr(rag.semantic_cache, "lookup", lookups)
    monkeypatch.setattr(rag.semantic_cache, "store", stores)

    middleware.answer_with_pii_protection("What is PM-KISAN?")

    lookups.assert_called_once()
    stores.assert_called_once()


def test_setting_disables_redaction_and_the_path_still_works(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    monkeypatch.setattr(settings, "enable_pii_vault", False)

    result = middleware.answer_with_pii_protection(f"my aadhaar {AADHAAR}")

    # Disabled means disabled: the raw identifier reaches the provider. This is
    # the documented escape hatch, not the default.
    assert AADHAAR in provider.payload_text()
    assert result["answer"]


def test_middleware_does_not_bypass_the_kill_switch(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    operator = MagicMock()
    operator.gate.return_value = "kill_switch"
    monkeypatch.setattr(rag, "operator", operator)
    monkeypatch.setattr(
        rag,
        "fallback_answer",
        lambda *a, **k: {
            "answer": "retrieval only",
            "sources": [],
            "mode": "degraded",
            "language": "en",
        },
    )

    result = middleware.answer_with_pii_protection(f"my aadhaar {AADHAAR}")

    assert result["mode"] == "degraded"
    assert provider.prompts == []


def test_no_pii_result_is_returned_unchanged(monkeypatch):
    provider = _RecordingProvider()
    _configure(monkeypatch, provider)
    question = "How much income support does PM-KISAN provide?"

    result = middleware.answer_with_pii_protection(question)

    assert "[[PII:" not in result["answer"]
    assert result["mode"] == "live"
