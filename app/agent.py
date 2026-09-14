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

from langchain_core.documents import Document

from app.catalog import scheme_name_variants
from app.db import fetch_generation_documents, fetch_generation_jurisdictions
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


def _require_generation(tool: str, corpus_generation: str | None) -> str:
    """Every answer-producing tool must be bound to one known generation.

    A tool that cannot be pinned could mix a live filesystem/catalog read with
    an earlier database generation, so it fails rather than answer unbound.
    """
    if not corpus_generation:
        raise ValueError(f"{tool} requires a known corpus generation")
    return corpus_generation


def search_schemes(
    query: str,
    jurisdiction: str | None = None,
    corpus_generation: str | None = None,
) -> list[Document]:
    """Hybrid-retrieve relevant docs, optionally filtered to a jurisdiction.

    ``corpus_generation`` pins the search to the request's captured generation.
    """
    from app.retrieval import HybridRetriever

    generation = _require_generation("search_schemes", corpus_generation)
    docs = HybridRetriever(corpus_generation=generation).invoke(query)
    if jurisdiction:
        narrowed = [
            d for d in docs
            if str(jurisdiction).lower() in str(d.metadata.get("jurisdiction", "")).lower()
        ]
        docs = narrowed or docs
    return docs


def get_scheme_details(
    scheme_id: str, corpus_generation: str | None = None
) -> list[Document]:
    """Return the recorded details of one scheme from the pinned corpus.

    Sourced only from the generation-pinned vector table (never the live
    filesystem/catalog), so an edited or deleted local Markdown file cannot be
    mixed into an answer bound to an earlier generation.
    """
    generation = _require_generation("get_scheme_details", corpus_generation)
    records = fetch_generation_documents(generation, source=scheme_id)
    if not records:
        return [
            Document(
                page_content=f"No scheme found for id '{scheme_id}'.",
                metadata={"source": scheme_id, "corpus_generation": generation},
            )
        ]
    content = "\n\n".join(
        str(record.get("content") or "") for record in records
    )
    metadata = dict(records[0].get("metadata") or {})
    metadata.setdefault("source", scheme_id)
    metadata["corpus_generation"] = generation
    return [Document(page_content=content[:2000], metadata=metadata)]


def list_jurisdictions(corpus_generation: str | None = None) -> list[Document]:
    """Jurisdictions present in the pinned corpus, not the static catalog."""
    generation = _require_generation("list_jurisdictions", corpus_generation)
    names = ", ".join(fetch_generation_jurisdictions(generation))
    return [
        Document(
            page_content=f"Covered jurisdictions: {names}",
            metadata={"source": "jurisdictions", "corpus_generation": generation},
        )
    ]


def _tool_map(corpus_generation: str) -> dict:
    generation = _require_generation("agent tools", corpus_generation)

    def _search(query: str, jurisdiction: str | None = None) -> list[Document]:
        return search_schemes(query, jurisdiction, generation)

    def _details(scheme_id: str) -> list[Document]:
        return get_scheme_details(scheme_id, generation)

    def _jurisdictions() -> list[Document]:
        return list_jurisdictions(generation)

    return {
        "search_schemes": _search,
        "get_scheme_details": _details,
        "list_jurisdictions": _jurisdictions,
    }


def _step_summary(name: str, args: dict, tool_docs: list[Document]) -> dict:
    query = args.get("query") or args.get("scheme_id") or list(args.keys())
    return {"tool": name, "summary": f"{query} → {len(tool_docs)} result(s)"}


def run_agent_gather(
    question: str,
    language: str = "en",
    profile=None,
    max_steps: int = MAX_STEPS,
    corpus_generation: str | None = None,
) -> tuple[list[Document], list[dict]]:
    """Tool-calling loop that gathers context documents + auditable steps.

    Returns ``(docs, steps)`` where ``docs`` is the deduplicated gathered
    context and ``steps`` records each tool call for the UI. Any failure before
    a final answer is raised; the caller should degrade to single-shot
    retrieval (never silently answer from an empty context).

    Every tool is bound to ``corpus_generation`` and every context document is
    read from that generation-pinned corpus, so agentic answers cannot mix a
    changed local file or catalog with an earlier database generation. A missing
    generation raises instead of running unbound tools.
    """
    lang = "hi" if str(language).strip().lower() == "hi" else "en"
    # Validate generation binding before any provider call: an unbound agent
    # must fail closed, not answer from mixed corpora.
    tool_map = _tool_map(corpus_generation)
    model = get_llm().bind_tools(TOOLS)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[lang]},
        {"role": "user", "content": question},
    ]
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
