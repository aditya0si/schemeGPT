"""Server-Sent Events streaming for POST /query/stream.

Event protocol (terminal event is always ``done`` or ``error``):
- ``sources``: list of retrieved source dicts (provenance included)
- ``token``:   ``{"text": str}`` answer fragment, in order
- ``done``:    ``{"mode": "live"|"degraded"|"demo", "notice": str|None, ...}``
- ``error``:   ``{"message": str}`` mid-stream failure notice

Live path: normalize the question (cheap LLM rewrite, best-effort), retrieve
from pgvector, then stream the stuff-documents chain answer tokens. Degraded
path (AI switched off, provider circuit open, or a provider failure before the
first token): stream a retrieval-only answer assembled from source excerpts.
Demo path (no key or unknown corpus generation): stream the pre-made demo
answer with the same labelled honesty as POST /query. A failure AFTER tokens
started emits ``error`` and closes; the client keeps the partial text.

PII (Phase 6c): the inbound question is tokenised with one request-scoped
``Vault`` before it reaches a provider, and every outbound token passes through
a bounded overlap buffer (``app.guardrails.stream``) that restores the
pre-generation placeholders and redacts identifiers found in the streamed text.
A PII-bearing request bypasses the semantic cache here too.
"""

import json
import logging
from typing import AsyncIterator

import anyio

from app import metrics, semantic_cache
from app.guardrails.stream import StreamRedactor
from app.ops import ops as operator
from app.rag import (
    _build_profile_context,
    _normalize_language,
    build_answer_chain,
    demo_answer,
    fallback_answer,
    get_llm,
    retrieve_context,
    TokenUsageHandler,
)
from app.config import settings
from app.quotes import parse_quotes, verify_quotes
from app.schemas import ProfileData
from app.tracing import stage_span

logger = logging.getLogger(__name__)

GENERIC_STREAM_ERROR = (
    "The live answer stream failed partway. This partial answer may be "
    "incomplete — please ask again."
)
GENERIC_STREAM_ERROR_HI = (
    "लाइव उत्तर स्ट्रीम बीच में विफल हो गया। यह आंशिक उत्तर अपूर्ण हो सकता है — "
    "कृपया दोबारा पूछें।"
)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _source_dict(doc) -> dict:
    return {
        "source": doc.metadata.get("source", ""),
        "content": doc.page_content,
        "jurisdiction": doc.metadata.get("jurisdiction"),
        "state": doc.metadata.get("state"),
        "data_status": doc.metadata.get("data_status"),
        "last_verified": doc.metadata.get("last_verified"),
        "source_url": doc.metadata.get("source_url"),
    }


async def _stream_fallback(payload: dict, lang: str) -> AsyncIterator[str]:
    """Stream a non-live payload (degraded or demo) in the standard event shape.

    ``sources`` -> ``token``* -> ``quotes`` -> ``done``. The ``done`` event
    carries the payload's own ``mode`` (``degraded`` or ``demo``) and notice,
    so a client can distinguish "AI is switched off, here are source excerpts"
    from "no live service configured, here is a demo answer".
    """
    sources = payload.get("sources", [])
    answer_text = payload.get("answer", "")
    yield _sse("sources", sources)
    for word in answer_text.split(" "):
        yield _sse("token", {"text": word + " "})
    quoted = verify_quotes(parse_quotes(answer_text), sources)
    if quoted:
        yield _sse("quotes", [q.__dict__ for q in quoted])
    mode = payload.get("mode", "demo")
    metrics.inc("queries_degraded" if mode == "degraded" else "queries_demo")
    yield _sse(
        "done",
        {
            "mode": mode,
            "notice": payload.get("notice"),
            "language": payload.get("language", lang),
        },
    )


async def _stream_answer_core(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
    *,
    skip_cache: bool = False,
) -> AsyncIterator[str]:
    lang = _normalize_language(language)
    profile_context = _build_profile_context(profile, lang)

    # Keep demo-mode requests database-free and match synchronous behavior.
    # Handled outside the provider-failure boundary deliberately: an
    # unconfigured instance is not a failing provider and must not count
    # against the circuit breaker.
    if not settings.groq_api_key.strip():
        demo = await anyio.to_thread.run_sync(demo_answer, question, lang)
        async for event in _stream_fallback(demo, lang):
            yield event
        return

    tokens_sent = False
    answer_parts: list[str] = []
    try:
        # Operator state, consulted once. The kill switch bypasses the semantic
        # cache (stop serving generated text, not just stop generating it) while
        # the breaker does not (an availability problem should still be able to
        # answer from cache). See app/rag.answer for the full reasoning.
        gate = operator.gate()
        if gate == "kill_switch":
            payload = await anyio.to_thread.run_sync(
                lambda: fallback_answer(question, lang, profile, reason=gate)
            )
            async for event in _stream_fallback(payload, lang):
                yield event
            return
        # Capture the corpus generation once and carry it through lookup,
        # retrieval, and store, matching the synchronous /query path exactly.
        # An unknown generation fails closed: the stream returns the labelled
        # demo answer rather than running an unbound retrieval or an unnamed
        # cache namespace.
        try:
            generation = await anyio.to_thread.run_sync(
                semantic_cache.capture_generation
            )
        except Exception as exc:
            logger.error(
                "Corpus generation metadata unavailable (%s); streaming demo "
                "answer.",
                type(exc).__name__,
            )
            demo = await anyio.to_thread.run_sync(demo_answer, question, lang)
            async for event in _stream_fallback(demo, lang):
                yield event
            return
        if not generation:
            logger.error(
                "Corpus generation is uninitialized; streaming demo answer."
            )
            demo = await anyio.to_thread.run_sync(demo_answer, question, lang)
            async for event in _stream_fallback(demo, lang):
                yield event
            return
        # Semantic cache: serve a stored live answer for a semantically equal
        # question (same language + profile) with the identical event shape.
        ph = semantic_cache.profile_hash(profile)
        cached = None
        if not skip_cache:
            cached = await anyio.to_thread.run_sync(
                semantic_cache.lookup, question, lang, ph, generation
            )
        if cached is not None:
            cached = semantic_cache.revalidate_payload(cached)
            yield _sse("sources", cached.get("sources", []))
            answer_text = cached.get("answer", "")
            for i in range(0, len(answer_text), 80):
                yield _sse("token", {"text": answer_text[i : i + 80]})
            if cached.get("quotes"):
                yield _sse("quotes", cached["quotes"])
            metrics.inc("queries_live")
            yield _sse(
                "done",
                {"mode": "live", "notice": None, "language": lang, "cached": True},
            )
            return
        if gate == "breaker":
            payload = await anyio.to_thread.run_sync(
                lambda: fallback_answer(question, lang, profile, reason=gate)
            )
            async for event in _stream_fallback(payload, lang):
                yield event
            return
        # A valid cache hit avoids a provider call; a miss validates the client
        # before retrieval and falls back cleanly if provider setup is invalid.
        get_llm()
        with stage_span("retrieve") as span:
            docs, steps = await anyio.to_thread.run_sync(
                retrieve_context, question, lang, profile, generation
            )
            if span is not None:
                span.set_attribute("docs.count", len(docs))
        for step in steps:
            yield _sse("step", step)
        source_payload = [_source_dict(doc) for doc in docs]
        yield _sse("sources", source_payload)
        chain = build_answer_chain(lang)
        usage = TokenUsageHandler()
        with stage_span("generate"):
            async for chunk in chain.astream(
                {
                    "context": docs,
                    "input": question,
                    "profile_context": profile_context,
                },
                config={"callbacks": [usage]},
            ):
                text = chunk if isinstance(chunk, str) else str(chunk)
                if not text:
                    continue
                tokens_sent = True
                answer_parts.append(text)
                yield _sse("token", {"text": text})
        with stage_span("verify_quotes"):
            verified = verify_quotes(
                parse_quotes("".join(answer_parts)), source_payload
            )
        if verified:
            yield _sse("quotes", [q.__dict__ for q in verified])
        usage.record(settings.groq_model)
        operator.record_provider_success()
        metrics.inc("queries_live")
        if not skip_cache:
            await anyio.to_thread.run_sync(
                semantic_cache.store,
                question,
                lang,
                ph,
                {
                    "answer": "".join(answer_parts),
                    "sources": source_payload,
                    "quotes": [q.__dict__ for q in verified] if verified else [],
                    "mode": "live",
                    "language": lang,
                },
                generation,
            )
        yield _sse("done", {"mode": "live", "notice": None, "language": lang})
    except Exception as exc:
        if tokens_sent:
            metrics.inc("stream_midstream_failures")
            operator.record_provider_failure(type(exc).__name__)
            logger.error(
                "Live stream failed mid-answer (%s).", type(exc).__name__
            )
            yield _sse(
                "error",
                {
                    "message": (
                        GENERIC_STREAM_ERROR_HI
                        if lang == "hi"
                        else GENERIC_STREAM_ERROR
                    )
                },
            )
            return
        opened = operator.record_provider_failure(type(exc).__name__)
        logger.error(
            "Live stream failed before answer (%s); streaming retrieval-only "
            "answer%s.",
            type(exc).__name__,
            " and opening the provider circuit" if opened else "",
        )
        payload = await anyio.to_thread.run_sync(
            lambda: fallback_answer(
                question, lang, profile, reason="provider_failure"
            )
        )
        async for event in _stream_fallback(payload, lang):
            yield event


def _parse_event(part: str) -> tuple[str | None, dict | None]:
    """Decode one SSE block emitted by :func:`_sse` (name, data)."""
    name: str | None = None
    data: dict | None = None
    for line in part.split("\n"):
        if line.startswith("event: "):
            name = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])
    return name, data


async def stream_answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
) -> AsyncIterator[str]:
    """Stream an answer with request-scoped PII redaction (Phase 6c).

    One fresh ``Vault`` is created for the request. The question is tokenised
    with it before it reaches retrieval or a provider; ``_stream_answer_core``
    then runs with the redacted question and, when PII was present, with the
    semantic cache bypassed (the same cross-request rule as ``POST /query``).

    Every outbound ``token`` is passed through a :class:`StreamRedactor`, a
    bounded overlap buffer that restores the placeholders the question produced
    and redacts any raw identifier found in the streamed text. The held tail is
    flushed once, immediately before the first ``quotes``/``done`` event, so
    token events still precede both terminal events. On a mid-stream ``error``
    or a client disconnect the tail is discarded, never emitted.
    """
    if not getattr(settings, "enable_pii_vault", True):
        async for part in _stream_answer_core(question, language, profile):
            yield part
        return

    redactor, redacted_question = StreamRedactor.for_question(question)
    flushed = False
    saw_error = False
    try:
        async for part in _stream_answer_core(
            redacted_question,
            language,
            profile,
            skip_cache=redactor.has_pii,
        ):
            name, data = _parse_event(part)
            if name == "token":
                safe = redactor.feed(data.get("text", "") if data else "")
                if safe:
                    yield _sse("token", {"text": safe})
                continue
            if name == "error":
                saw_error = True
            if name in ("quotes", "done") and not flushed:
                tail = redactor.flush()
                flushed = True
                if tail:
                    yield _sse("token", {"text": tail})
            yield part
        if not flushed and not saw_error:
            tail = redactor.flush()
            flushed = True
            if tail:
                yield _sse("token", {"text": tail})
    finally:
        if not flushed:
            redactor.discard()
