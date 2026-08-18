"""Agentic multi-step retrieval for complex SchemeGPT questions.

Single-shot retrieval answers most questions well, but comparative, multi-scheme,
or profile-aware questions ("PM-KISAN vs PM-SYM for me") need several lookups. A
naive one-pass retrieval can't stitch those together. This module adds a small
tool-calling loop (no new dependencies): the LLM may call ``search_schemes``,
``get_scheme_details``, or ``list_jurisdictions`` up to a bounded number of
times, we collect the resulting context documents and an auditable list of
``steps``, and the caller streams a final answer from that gathered context.

Only the cheap heuristic ``needs_multi_step`` decides routing (a fast
pretest, not an LLM call). No key/DB is needed when the question is simple.
"""

import json
import logging
from pathlib import Path

from langchain_core.documents import Document

from app.catalog import (
    load_schemes_by_source,
    load_states_catalog,
    scheme_name_variants,
)
from app.config import ROOT_DIR
from app.rag import SYSTEM_PROMPTS, get_llm

logger = logging.getLogger(__name__)

MAX_STEPS = 3

COMPARATIVE_MARKERS = (
    " vs", "vs.", " or ", "compare", "comparison", "difference",
    "which is better", "better", "तुलना", " या ",
)
PROFILE_MARKERS = ("me", "my", "मेरे", "मेरा", "mera")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_schemes",
            "description": "Search the scheme/law corpus for documents relevant to a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "free-text search query"},
                    "jurisdiction": {"type": "string", "description": "optional state/UT filter"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scheme_details",
            "description": "Get the full recorded details of one scheme by its id or filename.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scheme_id": {"type": "string", "description": "e.g. pm-kisan.md"},
                },
                "required": ["scheme_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_jurisdictions",
            "description": "List all states/UTs covered by the corpus.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def needs_multi_step(question: str, profile=None) -> bool:
    """Cheap heuristic: does this question benefit from tool-calling retrieval?"""
    q = str(question).lower()
    if any(marker in q for marker in COMPARATIVE_MARKERS):
        return True
    mentions = sum(1 for name in scheme_name_variants() if name in q)
    if mentions >= 2:
        return True
    if profile is not None and any(marker in q for marker in PROFILE_MARKERS):
        return True
    return False


def search_schemes(query: str, jurisdiction: str | None = None) -> list[Document]:
    """Hybrid-retrieve relevant docs, optionally filtered to a jurisdiction."""
    from app.retrieval import HybridRetriever

    docs = HybridRetriever().invoke(query)
    if jurisdiction:
        narrowed = [
            d for d in docs
            if str(jurisdiction).lower() in str(d.metadata.get("jurisdiction", "")).lower()
        ]
        docs = narrowed or docs
    return docs


def get_scheme_details(scheme_id: str) -> list[Document]:
    """Return the recorded details of one scheme as a document."""
    records = load_schemes_by_source()
    for source, record in records.items():
        if scheme_id in source or source.endswith(scheme_id):
            rel = source[5:] if source.startswith("data/") else source
            path = ROOT_DIR / "data" / rel
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            return [
                Document(
                    page_content=text[:1500],
                    metadata={
                        "source": source,
                        "data_status": record.get("data_status"),
                        "jurisdiction": record.get("jurisdiction"),
                    },
                )
            ]
    return [
        Document(
            page_content=f"No scheme found for id '{scheme_id}'.",
            metadata={"source": scheme_id},
        )
    ]


def list_jurisdictions() -> list[Document]:
    names = ", ".join(str(r.get("name")) for r in load_states_catalog() if r.get("name"))
    return [
        Document(page_content=f"Covered jurisdictions: {names}", metadata={"source": "jurisdictions"})
    ]


def _tool_map() -> dict:
    return {
        "search_schemes": search_schemes,
        "get_scheme_details": get_scheme_details,
        "list_jurisdictions": list_jurisdictions,
    }


def _step_summary(name: str, args: dict, tool_docs: list[Document]) -> dict:
    query = args.get("query") or args.get("scheme_id") or list(args.keys())
    return {"tool": name, "summary": f"{query} → {len(tool_docs)} result(s)"}


def run_agent_gather(
    question: str,
    language: str = "en",
    profile=None,
    max_steps: int = MAX_STEPS,
) -> tuple[list[Document], list[dict]]:
    """Tool-calling loop that gathers context documents + auditable steps.

    Returns ``(docs, steps)`` where ``docs`` is the deduplicated gathered
    context and ``steps`` records each tool call for the UI. Any failure before
    a final answer is raised; the caller should degrade to single-shot
    retrieval (never silently answer from an empty context).
    """
    lang = "hi" if str(language).strip().lower() == "hi" else "en"
    model = get_llm().bind_tools(TOOLS)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[lang]},
        {"role": "user", "content": question},
    ]
    tool_map = _tool_map()
    docs: list[Document] = []
    steps: list[dict] = []
    seen: set[tuple] = set()

    for _ in range(max_steps):
        response = model.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(response)
        for call in tool_calls:
            call_id = call.get("id")
            name = call.get("name") or call.get("function", {}).get("name")
            raw = call.get("args") or json.loads(call.get("function", {}).get("arguments") or "{}")
            fn = tool_map.get(name)
            if fn is None:
                messages.append({"role": "tool", "tool_call_id": call_id, "content": "unknown tool"})
                continue
            try:
                tool_docs = fn(**raw)
            except Exception as exc:  # a tool failing must not kill the loop
                logger.warning("Agent tool '%s' failed: %s", name, type(exc).__name__)
                tool_docs = [Document(page_content=f"tool {name} failed: {type(exc).__name__}")]
            steps.append(_step_summary(name, raw, tool_docs))
            readable = "\n\n".join(d.page_content for d in tool_docs)[:4000]
            messages.append({"role": "tool", "tool_call_id": call_id, "content": readable})
            for doc in tool_docs:
                key = (doc.metadata.get("source", ""), doc.page_content[:80])
                if key not in seen:
                    seen.add(key)
                    docs.append(doc)
    else:
        # Loop exhausted without a final answer; degrade gracefully.
        logger.warning("Agent loop hit the %d-step cap; answering from gathered context.", max_steps)

    if not docs:
        raise RuntimeError("agent gathered no context")
    return docs, steps
