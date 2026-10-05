"""Attach samjho's frozen ``api/`` callables to the SchemeGPT spine.

samjho (staged read-only at ``.hermes/ref/samjho/``) freezes
``api.retriever.search`` and ``api.answer.answer_question`` over the logical
names ``question`` / ``subject`` / ``chapter_no`` / ``top_k``. It is not
installed here, so this module takes those callables by injection and never
imports samjho at import time. A binding is subject-scoped: ``subject`` /
``chapter_no`` / ``top_k`` are fixed at build time and ``question`` arrives per
request; the four logical names are mapped onto the injected callable's declared
parameter names (the job samjho's own ``evals/adapter._bind`` does).

samjho's three answer paths (written / retrieval-only / refusal) stay visible as
``path`` plus ``refused`` / ``provider`` / ``degraded``. The spine's mode
vocabulary has no word for a refusal, so a refusal is ``mode="degraded"`` with
``refused=True``; and ``api.retriever.search`` has no spine seam because
retrieval is inside the answer unit (see ``docs/evidence/SPINE-SECOND-CLIENT.md``).
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from app.core.seams import Spine

_ALIASES: dict[str, tuple[str, ...]] = {
    "question": ("question", "query", "q", "text", "prompt", "user_question"),
    "subject": ("subject", "subject_id", "subject_name"),
    "chapter_no": ("chapter_no", "chapter_number", "chapter_num", "chapter", "chapter_id"),
    "top_k": ("top_k", "k", "limit", "n", "num_results", "top_n"),
}


def _logical_for(param: str) -> str | None:
    lowered = param.lower()
    return next(
        (logical for logical, names in _ALIASES.items() if lowered in names), None
    )


def _bind(fn: Callable[..., Any], values: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    """Map logical values onto the parameters ``fn`` actually declares."""
    positional: list[Any] = []
    kwargs: dict[str, Any] = {}
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        logical = _logical_for(name)
        if logical is None or values.get(logical) is None:
            continue
        if param.kind is param.POSITIONAL_ONLY:
            positional.append(values[logical])
        else:
            kwargs[name] = values[logical]
    return positional, kwargs


def _invoke(fn: Callable[..., Any], question: str, scope: dict[str, Any]) -> Any:
    positional, kwargs = _bind(fn, {"question": question, **scope})
    return fn(*positional, **kwargs)


def _as_dict(obj: Any) -> dict[str, Any]:
    """Normalise a pydantic model / dataclass / mapping into a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dict(dump())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return {k: v for k, v in getattr(obj, "__dict__", {}).items() if not k.startswith("_")}


def _sources(citations: list[Any]) -> list[dict[str, Any]]:
    """samjho citations -> spine source dicts, tagged with their citation label."""
    sources = []
    for citation in citations:
        data = _as_dict(citation)
        start = int(data.get("page_start") or 0)
        end = int(data.get("page_end") or start)
        pages = f"p.{start}" if end <= start else f"pp.{start}-{end}"
        label = f"[Ch {data.get('chapter_no')} §{data.get('section_no')} {pages}]"
        data.setdefault("citation_label", label)
        data.setdefault("source", label)
        data.setdefault("content", str(data.get("text") or ""))
        sources.append(data)
    return sources


def _quote_records(answer_text: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The spine's ``VerifiedQuote`` shape (text/source/status/verified/matched_source)."""
    text = answer_text or ""

    def record(source: dict[str, Any]) -> dict[str, Any]:
        label = str(source.get("citation_label") or source.get("source") or "")
        matched = source.get("chunk_id") or source.get("id")
        return {
            "text": str(source.get("content") or label),
            "source": label,
            "status": source.get("data_status"),
            "verified": bool(label) and label in text,
            "matched_source": None if matched is None else str(matched),
        }

    return [record(source) for source in sources]


def _answer_dict(payload: dict[str, Any], language: str) -> dict[str, Any]:
    """samjho's AnswerResult -> the spine answer payload, answer path preserved."""
    citations = _sources(list(payload.get("citations") or []))
    refused = bool(payload.get("refused"))
    provider = str(payload.get("provider") or "")
    degraded = bool(payload.get("degraded"))
    if refused:
        path = "refusal"
    elif provider and provider != "retrieval-only":
        path = "written"
    else:
        path = "retrieval-only"
    answer_text = str(payload.get("answer") or "")
    return {
        "answer": answer_text,
        "sources": citations,
        "quotes": _quote_records(answer_text, citations),
        "mode": "live" if path == "written" else "degraded",
        "path": path,
        "refused": refused,
        "refusal_reason": payload.get("refusal_reason"),
        "provider": provider,
        "degraded": degraded,
        "stripped_citations": int(payload.get("stripped_citations") or 0),
        "language": language,
    }


def _no_router(role: str = "answer", max_tokens: int = 1024) -> Any:
    raise NotImplementedError("samjho runs its provider inside api.answer; no router seam")


@dataclass(frozen=True)
class SamjhoBinding:
    """The attached spine, plus samjho's retrieval surface (no spine seam)."""

    spine: Spine
    retrieve: Callable[..., list[dict[str, Any]]]


def bind_samjho(
    answer_question: Callable[..., Any],
    *,
    subject: str,
    search: Callable[..., Any] | None = None,
    gate: Callable[[], str] | None = None,
    router: Callable[..., Any] | None = None,
    stream: Callable[..., AsyncIterator[str]] | None = None,
    chapter_no: int | None = None,
    top_k: int = 6,
) -> SamjhoBinding:
    """Inject samjho's callables and return a ``SamjhoBinding``."""
    scope = {"subject": subject, "chapter_no": chapter_no, "top_k": top_k}

    def answerer(question, language="en", profile=None, *, skip_cache=False):
        return _answer_dict(_as_dict(_invoke(answer_question, question, scope)), language)

    def validator(answer_text, sources):
        return _quote_records(answer_text, list(sources))

    def egress(question, language="en", profile=None):
        return answerer(question, language, profile)

    async def streamer(question, language="en", profile=None):
        payload = egress(question, language, profile)
        yield f"event: sources\ndata: {json.dumps({'sources': payload['sources']})}\n\n"
        yield f"event: token\ndata: {json.dumps({'text': payload['answer']})}\n\n"
        done = {"refused": payload["refused"], "provider": payload["provider"]}
        yield f"event: done\ndata: {json.dumps(done)}\n\n"

    def retrieve(question, **extra):
        if search is None:
            raise NotImplementedError("no samjho search callable was injected")
        hits = _invoke(search, question, {**scope, **extra})
        return [_as_dict(hit) for hit in hits]

    spine = Spine(
        gate=gate or (lambda: "ok"),
        router=router or _no_router,
        answerer=answerer,
        validator=validator,
        egress=egress,
        stream=stream or streamer,
    )
    return SamjhoBinding(spine=spine, retrieve=retrieve)
