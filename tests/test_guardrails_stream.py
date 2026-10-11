"""Phase 6c overlap-buffering battery for the streaming PII redactor.

The whole point of this phase is the chunk boundary: an identifier (or a
placeholder) split across two SSE chunks must never be emitted half-formed.
Every test here drives the synthetic stream directly through
:class:`app.guardrails.stream.StreamRedactor` and, for the integration cases,
through the real ``app.stream.stream_answer`` with a stubbed provider. No
network and no database.

Test data is synthetic: ``AADHAAR`` is a checksum-valid number reused from the
Phase 6a/6b suites, never a real person's identifier.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

import app.stream as stream
from app.config import settings
from app.guardrails.recognizers import find_all
from app.guardrails.stream import HOLDBACK, StreamRedactor
from app.guardrails.vault import PLACEHOLDER_RE, Vault

# Synthetic and checksum-valid (see tests/test_guardrails_recognizers.py).
AADHAAR = "234123412346"

# A deterministic nonce makes the minted placeholder predictable, so the tests
# can assert an exact byte-for-byte expected stream rather than a fuzzy shape.
NONCE = "00000000"
AADHAAR_PLACEHOLDER = f"[[PII:{NONCE}:AADHAAR:1]]"

REDACTION_TEXT = f"Your number is {AADHAAR} for the scheme."
RESTORATION_ANSWER = f"Registered under {AADHAAR_PLACEHOLDER} today."


def _redactor():
    """A redactor over one deterministic request-scoped vault."""
    return StreamRedactor(Vault(nonce=NONCE))


def _session(question: str):
    """Vault + redactor for a question, exactly as ``stream_answer`` builds it."""
    vault = Vault(nonce=NONCE)
    redacted_question, _ = vault.tokenize(question)
    placeholders = PLACEHOLDER_RE.findall(redacted_question)
    return StreamRedactor(vault, placeholders), redacted_question


def _drive(redactor: StreamRedactor, text: str, split: int) -> str:
    """Feed ``text`` in exactly two pieces at ``split`` and flush."""
    return (
        redactor.feed(text[:split])
        + redactor.feed(text[split:])
        + redactor.flush()
    )


def _sse_events(text: str):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


# --------------------------------------------------------------------------
# R2: the hold-back is bounded and derived, not the whole stream
# --------------------------------------------------------------------------


def test_holdback_is_derived_and_covers_every_bounded_pattern():
    # Longest bounded recognizer match: GSTIN (2+5+4+1+3 = 15). Longest
    # placeholder: 6 + 8 + 1 + len("DEVANAGARI_DIGITS") + 1 + index + 2 = 39 for
    # a four-digit index. HOLDBACK must clear both.
    assert HOLDBACK >= 15
    assert HOLDBACK >= 39


def test_a_long_stream_emits_progressively_not_only_at_flush():
    redactor = _redactor()
    head = "policy text " * 40  # 480 characters, no identifiers
    first = redactor.feed(head)
    assert first, "a bounded hold-back must not buffer the whole stream"
    rest = redactor.feed("end") + redactor.flush()
    assert first + rest == head + "end"


# --------------------------------------------------------------------------
# R5: identifier split across EVERY boundary is never emitted unredacted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("split", range(1, len(REDACTION_TEXT)))
def test_identifier_split_at_every_boundary_is_never_emitted_unredacted(split):
    expected = REDACTION_TEXT.replace(AADHAAR, AADHAAR_PLACEHOLDER)
    emitted = _drive(_redactor(), REDACTION_TEXT, split)
    # Byte-exact: no prefix of the identifier, and no fragment, can survive.
    assert emitted == expected
    assert AADHAAR not in emitted
    assert find_all(emitted) == []


# --------------------------------------------------------------------------
# R5: placeholder split across EVERY boundary is restored whole
# --------------------------------------------------------------------------


@pytest.mark.parametrize("split", range(1, len(RESTORATION_ANSWER)))
def test_placeholder_split_at_every_boundary_is_restored_whole(split):
    redactor, _ = _session(f"my aadhaar is {AADHAAR}")
    expected = RESTORATION_ANSWER.replace(AADHAAR_PLACEHOLDER, AADHAAR)
    emitted = _drive(redactor, RESTORATION_ANSWER, split)
    assert emitted == expected
    assert "[[PII" not in emitted
    assert AADHAAR in emitted


# --------------------------------------------------------------------------
# R5: the split lands exactly on the hold-back edge
# --------------------------------------------------------------------------


@pytest.mark.parametrize("prefix_len", [HOLDBACK - 1, HOLDBACK, HOLDBACK + 1])
def test_split_at_the_holdback_edge(prefix_len):
    text = "x" * prefix_len + AADHAAR + " end"
    # Split the identifier down the middle, with its start exactly at the edge.
    first = text[: prefix_len + 6]
    emitted = _drive(_redactor(), text, len(first))
    assert emitted == text.replace(AADHAAR, AADHAAR_PLACEHOLDER)
    assert AADHAAR not in emitted


# --------------------------------------------------------------------------
# R5: trailing identifier at end-of-stream is resolved by the flush
# --------------------------------------------------------------------------


def test_trailing_identifier_is_resolved_by_the_flush():
    redactor = _redactor()
    text = f"number {AADHAAR}"
    assert redactor.feed(text) == "", "the whole short stream is held back"
    assert AADHAAR in redactor.pending
    assert redactor.flush() == f"number {AADHAAR_PLACEHOLDER}"
    assert redactor.pending == ""


def test_trailing_identifier_after_emitted_prefix_is_flushed_redacted():
    redactor = _redactor()
    prefix = "x" * (HOLDBACK + 5)
    out = redactor.feed(prefix + f" {AADHAAR}")
    out += redactor.flush()
    assert AADHAAR not in out
    assert out == (prefix + f" {AADHAAR}").replace(
        AADHAAR, AADHAAR_PLACEHOLDER
    )


# --------------------------------------------------------------------------
# R5: no PII passes through byte-identical and in order
# --------------------------------------------------------------------------


def test_no_pii_stream_is_byte_identical_and_in_order():
    redactor = _redactor()
    parts = ["The scheme ", "covers eligible ", "farmer families."]
    emitted = "".join(redactor.feed(part) for part in parts) + redactor.flush()
    assert emitted == "".join(parts)


def test_disabled_redactor_leaves_the_stream_byte_identical():
    redactor = StreamRedactor(Vault(nonce=NONCE), enabled=False)
    text = f"number {AADHAAR}"
    assert redactor.feed(text) == text
    assert redactor.flush() == ""


# --------------------------------------------------------------------------
# R5: request-scoped isolation on the streaming path
# --------------------------------------------------------------------------


def test_streaming_request_scope_isolation():
    question = f"my aadhaar is {AADHAAR}"
    redactor_a, _ = _session(question)
    vault_b = Vault(nonce="bbbbbbbb")
    redacted_b, _ = vault_b.tokenize(question)
    redactor_b = StreamRedactor(vault_b, PLACEHOLDER_RE.findall(redacted_b))

    placeholder_a = AADHAAR_PLACEHOLDER
    assert placeholder_a not in redacted_b  # per-request nonce

    answer = f"reference {placeholder_a} here"
    out_b = redactor_b.feed(answer) + redactor_b.flush()
    assert placeholder_a in out_b, "B must not restore A's placeholder"
    assert AADHAAR not in out_b

    out_a = redactor_a.feed(answer) + redactor_a.flush()
    assert AADHAAR in out_a
    assert placeholder_a not in out_a


# --------------------------------------------------------------------------
# R3: error / disconnect never emits the held-back tail
# --------------------------------------------------------------------------


def test_discard_drops_the_held_tail_without_emitting_a_fragment():
    redactor = _redactor()
    text = f"number {AADHAAR}"
    assert redactor.feed(text) == ""
    assert AADHAAR in redactor.pending  # held, not emitted
    redactor.discard()
    assert redactor.pending == ""
    assert redactor.flush() == ""


# --------------------------------------------------------------------------
# Integration: the real stream_answer path
# --------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _EchoChain:
    """A stubbed answer chain that echoes the (redacted) provider prompt."""

    def __init__(self, captured: list):
        self._captured = captured

    async def astream(self, payload, config):
        self._captured.append(payload["input"])
        yield payload["input"]


class _BoomChain:
    """Yields one answer chunk, then fails mid-stream."""

    def __init__(self, text: str):
        self._text = text

    async def astream(self, payload, config):
        yield self._text
        raise RuntimeError("provider dropped the stream")


def _configure_stream(monkeypatch, chain):
    source = Document(
        page_content="Policy fact.",
        metadata={"source": "schemes/fact.md", "data_status": "sample_verified"},
    )
    monkeypatch.setattr(stream.settings, "groq_api_key", "configured")
    monkeypatch.setattr(stream.settings, "enable_pii_vault", True)
    monkeypatch.setattr(
        stream.semantic_cache, "capture_generation", lambda: "gen-1"
    )
    monkeypatch.setattr(stream.semantic_cache, "lookup", MagicMock(return_value=None))
    monkeypatch.setattr(stream.semantic_cache, "store", MagicMock())
    monkeypatch.setattr(stream, "retrieve_context", lambda *a, **k: ([source], []))
    monkeypatch.setattr(stream, "get_llm", lambda: object())
    monkeypatch.setattr(stream, "build_answer_chain", lambda language: chain)


@pytest.mark.anyio
async def test_question_is_redacted_before_provider_and_restored_to_client(
    monkeypatch,
):
    captured: list = []
    _configure_stream(monkeypatch, _EchoChain(captured))
    question = f"my aadhaar is {AADHAAR}, which schemes?"

    raw = "".join([part async for part in stream.stream_answer(question)])
    events = _sse_events(raw)

    assert captured, "the provider chain must have run"
    assert AADHAAR not in captured[0]
    assert find_all(captured[0]) == [], "no identifier reached the provider"
    assert "[[PII:" in captured[0]

    answer_text = "".join(
        data["text"] for name, data in events if name == "token"
    )
    assert AADHAAR in answer_text, "the citizen still sees their own value"


@pytest.mark.anyio
async def test_pii_stream_bypasses_the_semantic_cache(monkeypatch):
    captured: list = []
    chain = _EchoChain(captured)
    _configure_stream(monkeypatch, chain)
    lookup = MagicMock(return_value=None)
    store = MagicMock()
    monkeypatch.setattr(stream.semantic_cache, "lookup", lookup)
    monkeypatch.setattr(stream.semantic_cache, "store", store)

    _ = "".join(
        [
            part
            async for part in stream.stream_answer(f"my aadhaar is {AADHAAR}")
        ]
    )

    lookup.assert_not_called()
    store.assert_not_called()


@pytest.mark.anyio
async def test_clean_stream_still_uses_the_semantic_cache(monkeypatch):
    captured: list = []
    chain = _EchoChain(captured)
    _configure_stream(monkeypatch, chain)
    lookup = MagicMock(return_value=None)
    store = MagicMock()
    monkeypatch.setattr(stream.semantic_cache, "lookup", lookup)
    monkeypatch.setattr(stream.semantic_cache, "store", store)

    _ = "".join(
        [part async for part in stream.stream_answer("What is PM-KISAN?")]
    )

    lookup.assert_called_once()
    store.assert_called_once()


@pytest.mark.anyio
async def test_midstream_error_discards_the_held_tail(monkeypatch):
    # The leaked identifier sits in the held tail when the provider fails, so it
    # must never be emitted: a leak on an error path is still a leak.
    _configure_stream(monkeypatch, _BoomChain(f"number {AADHAAR}"))

    raw = "".join([part async for part in stream.stream_answer("question")])
    events = _sse_events(raw)

    assert events[-1][0] == "error"
    for name, data in events:
        assert name != "token", "the held tail must be discarded, not flushed"
        assert AADHAAR not in json.dumps(data)


@pytest.mark.anyio
async def test_setting_disabled_leaves_the_stream_byte_identical(monkeypatch):
    captured: list = []
    _configure_stream(monkeypatch, _EchoChain(captured))
    monkeypatch.setattr(stream.settings, "enable_pii_vault", False)
    question = f"my aadhaar is {AADHAAR}"

    raw = "".join([part async for part in stream.stream_answer(question)])

    assert AADHAAR in captured[0], "disabled means the raw value reaches the model"
    answer_text = "".join(
        data["text"] for name, data in _sse_events(raw) if name == "token"
    )
    assert answer_text == question
