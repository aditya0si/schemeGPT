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

from app.agent import needs_multi_step, run_agent_gather
from app.rag import (
    _build_profile_context,
    _normalize_language,
    build_answer_chain,
    demo_answer,
    get_llm,
    get_retriever,
    normalize_question,
)
from app.quotes import parse_quotes, verify_quotes
from app.schemas import ProfileData

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
        if needs_multi_step(question, profile):
            try:
                docs, steps = await anyio.to_thread.run_sync(
                    run_agent_gather, question, lang, profile
                )
            except Exception as exc:
                # Agent loop failed: degrade to single-shot retrieval rather
                # than dropping to demo mode for a live-configured stack.
                logger.warning("Agent retrieval failed (%s); single-shot path.", type(exc).__name__)
                normalized = await anyio.to_thread.run_sync(
                    normalize_question, question
                )
                docs = await anyio.to_thread.run_sync(
                    lambda: get_retriever().invoke(normalized)
                )
                steps = []
            for step in steps:
                yield _sse("step", step)
        else:
            normalized = await anyio.to_thread.run_sync(
                normalize_question, question
            )
            docs = await anyio.to_thread.run_sync(
                lambda: get_retriever().invoke(normalized)
            )
        yield _sse("sources", [_source_dict(doc) for doc in docs])
        chain = build_answer_chain(lang)
        async for chunk in chain.astream(
            {
                "context": docs,
                "input": question,
                "profile_context": profile_context,
            }
        ):
            text = chunk if isinstance(chunk, str) else str(chunk)
            if not text:
                continue
            tokens_sent = True
            answer_parts.append(text)
            yield _sse("token", {"text": text})
        verified = verify_quotes(parse_quotes("".join(answer_parts)), docs)
        if verified:
            yield _sse("quotes", [q.__dict__ for q in verified])
        yield _sse("done", {"mode": "live", "notice": None, "language": lang})
    except Exception as exc:
        if tokens_sent:
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
        logger.error(
            "Live stream failed before answer (%s); streaming demo answer.",
            type(exc).__name__,
        )
        demo = demo_answer(question, lang)
        yield _sse("sources", demo["sources"])
        for word in demo["answer"].split(" "):
            yield _sse("token", {"text": word + " "})
        demo_verified = verify_quotes(parse_quotes(demo["answer"]), demo["sources"])
        if demo_verified:
            yield _sse("quotes", [q.__dict__ for q in demo_verified])
        yield _sse(
            "done",
            {"mode": "demo", "notice": demo["notice"], "language": lang},
        )
