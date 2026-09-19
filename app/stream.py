"""Server-Sent Events streaming for POST /query/stream.

Event protocol (terminal event is always ``done`` or ``error``):
- ``sources``: list of retrieved source dicts (provenance included)
- ``token``:   ``{"text": str}`` answer fragment, in order
- ``done``:    ``{"mode": "live"|"demo", "notice": str|None, "language": ...}``
- ``error``:   ``{"message": str}`` mid-stream failure notice

Live path: normalize the question (cheap LLM rewrite, best-effort), retrieve
from pgvector, then stream the stuff-documents chain answer tokens. Demo path
(no key or any live failure before the first token): stream the pre-made demo
answer with the same labelled honesty as POST /query. A failure AFTER tokens
started emits ``error`` and closes; the client keeps the partial text.
"""

import json
import logging
from typing import AsyncIterator

import anyio

from app import metrics, semantic_cache
from app.agent import needs_multi_step, run_agent_gather
from app.ops import ops as operator
from app.rag import (
    _build_profile_context,
    _normalize_language,
    build_answer_chain,
    fallback_answer,
    get_llm,
    get_retriever,
    normalize_question,
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


async def stream_answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
) -> AsyncIterator[str]:
    lang = _normalize_language(language)
    profile_context = _build_profile_context(profile, lang)
    tokens_sent = False
    answer_parts: list[str] = []
    try:
        # Fail fast (no key -> ValueError) before touching the DB.
        get_llm()
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
        # Semantic cache: serve a stored live answer for a semantically equal
        # question (same language + profile) with the identical event shape.
        ph = semantic_cache.profile_hash(profile)
        cached = await anyio.to_thread.run_sync(
            semantic_cache.lookup, question, lang, ph
        )
        if cached is not None:
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
        if needs_multi_step(question, profile):
            metrics.inc("agent_routes_total")
            try:
                with stage_span("agent_gather"):
                    docs, steps = await anyio.to_thread.run_sync(
                        run_agent_gather, question, lang, profile
                    )
            except Exception as exc:
                # Agent loop failed: degrade to single-shot retrieval rather
                # than dropping to demo mode for a live-configured stack.
                logger.warning("Agent retrieval failed (%s); single-shot path.", type(exc).__name__)
                with stage_span("normalize"):
                    normalized = await anyio.to_thread.run_sync(
                        normalize_question, question
                    )
                with stage_span("retrieve") as span:
                    docs = await anyio.to_thread.run_sync(
                        lambda: get_retriever().invoke(normalized)
                    )
                    if span is not None:
                        span.set_attribute("docs.count", len(docs))
                steps = []
            for step in steps:
                yield _sse("step", step)
        else:
            with stage_span("normalize"):
                normalized = await anyio.to_thread.run_sync(
                    normalize_question, question
                )
            with stage_span("retrieve") as span:
                docs = await anyio.to_thread.run_sync(
                    lambda: get_retriever().invoke(normalized)
                )
                if span is not None:
                    span.set_attribute("docs.count", len(docs))
        yield _sse("sources", [_source_dict(doc) for doc in docs])
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
            verified = verify_quotes(parse_quotes("".join(answer_parts)), docs)
        if verified:
            yield _sse("quotes", [q.__dict__ for q in verified])
        usage.record(settings.groq_model)
        operator.record_provider_success()
        metrics.inc("queries_live")
        await anyio.to_thread.run_sync(
            semantic_cache.store,
            question,
            lang,
            ph,
            {
                "answer": "".join(answer_parts),
                "sources": [_source_dict(doc) for doc in docs],
                "quotes": [q.__dict__ for q in verified] if verified else [],
                "mode": "live",
                "language": lang,
            },
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
