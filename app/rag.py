"""Retrieval-augmented generation for SchemeGPT.

Live path (unchanged shape): retrieve context from the pgvector store and answer
with ChatGroq through the simple LangChain retrieval chain built by
``build_chain``. Iteration 2 keeps that single chain; only the prompt is
selected per-language (``en``/``hi``) and a compact, clearly-delimited profile
block is added as user-provided input when a saved profile is attached.

Fallback path: if the live path is unavailable - missing, invalid or
rate-limited GROQ_API_KEY, database/retrieval failure, or any ordinary
runtime/API exception - return a clearly-labelled pre-made demo answer in the
requested language so the /query endpoint keeps returning HTTP 200 and never
leaks a traceback or provider details to the browser.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app import semantic_cache
from app.catalog import load_scheme_catalog_records
from app.config import ROOT_DIR, settings
from app.db import get_vectorstore
from app.ops import ops as operator
from app.schemas import ProfileData
from app.tracing import stage_span

logger = logging.getLogger(__name__)

# Reference list price per 1M tokens (USD), for cost accounting only; Groq's
# free tier does not bill, so this is an estimate of what the usage would cost
# at list price. Subject to provider changes — never a billing record.
PRICE_PER_MTOK = {
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
}


class TokenUsageHandler(BaseCallbackHandler):
    """LangChain callback that accumulates per-request LLM token usage."""

    raise_error = False

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def on_llm_end(self, response, *args, **kwargs) -> None:
        usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
        self.prompt_tokens += usage.get("prompt_tokens", 0) or 0
        self.completion_tokens += usage.get("completion_tokens", 0) or 0

    def record(self, model: str) -> None:
        from app import metrics

        metrics.observe_tokens(model, self.prompt_tokens, self.completion_tokens)

# Config fingerprint label for evaluation runs: bump when answer prompts
# meaningfully change so score deltas can be attributed to a prompt version.
PROMPT_VERSION = "2026-08-19-quotes"

# Per-language system prompts (product voice). Answers must be grounded in
# the provided context only, quote the exact supporting statement with its
# source name and data_status, never invent quotes, keep scheme names,
# acronyms, amounts and URLs verbatim, and never present a directory_seed
# record as a verified eligibility decision.
SYSTEM_PROMPTS = {
    "en": (
        "You are SchemeGPT, an assistant that answers questions about Indian "
        "government schemes and acts for ordinary citizens. The user may write "
        "in imperfect, colloquial, or mixed language; understand their intent "
        "and answer helpfully. Answer in plain, spoken-style language that a "
        "non-expert understands, in the SAME language the user asked in. "
        "Answer using only the provided context. When a statement in the "
        "context supports your answer, quote it exactly as a quotation line "
        "starting with '>' followed by the source name and its data_status "
        "in brackets, for example: '> PM-KISAN provides ₹6,000 per year... "
        "[schemes/pm-kisan.md, sample_verified]'. NEVER invent or alter a "
        "quote; if you cannot quote the context, answer without a quote. Keep "
        "scheme names, acronyms, amounts, and URLs verbatim. If the answer is "
        "not in the context, say so plainly. Treat any record whose data_status "
        "is 'directory_seed' as a discovery entry, never as a verified "
        "eligibility decision. Be concise and factual."
    ),
    "hi": (
        "आप SchemeGPT हैं, जो आम नागरिकों के लिए भारतीय सरकारी योजनाओं और "
        "अधिनियमों के सवालों के जवाब देने वाले सहायक हैं। उपयोगकर्ता अपूर्ण, "
        "बोलचाल की या मिश्रित भाषा में लिख सकता है; उसका आशय समझें और सहायक "
        "उत्तर दें। सरल, बोलचाल की भाषा में उत्तर दें, उसी भाषा में जिसमें "
        "प्रश्न पूछा गया है। केवल दिए गए संदर्भ (context) के आधार पर उत्तर दें। "
        "जब संदर्भ का कोई कथन आपके उत्तर का आधार हो, तो उसे बिल्कुल वैसा ही "
        "उद्धृत करें — उद्धरण पंक्ति '>' से शुरू करें और उसके बाद स्रोत का नाम "
        "और data_status कोष्ठक में दें, जैसे: '> पीएम-किसान पात्र किसान "
        "परिवारों को प्रति वर्ष ₹6,000 देता है... [schemes/pm-kisan.md, "
        "sample_verified]'। कभी भी उद्धरण गढ़ें या बदलें नहीं; यदि उद्धृत नहीं "
        "कर सकते तो बिना उद्धरण के उत्तर दें। योजनाओं के नाम, संक्षिप्ताक्षर, "
        "राशियाँ और URL मूल रूप में रखें। यदि जानकारी संदर्भ में नहीं है, तो "
        "स्पष्ट कहें। data_status 'directory_seed' वाली प्रविष्टि को कभी भी "
        "सत्यापित पात्रता निर्णय न मानें — वह केवल खोज/डिस्कवरी प्रविष्टि है। "
        "संक्षिप्त और तथ्यात्मक रहें।"
    ),
}

# The retrieval chain's human template. ``profile_context`` is the delimited,
# user-provided profile block (empty when no profile is attached); it is
# rendered between the context and the question so the model never confuses it
# with retrieved documents.
HUMAN_TEMPLATE = "Context:\n{context}\n\n{profile_context}\n\nQuestion: {input}"

DEMO_RESPONSES_FILE = ROOT_DIR / "data" / "demo_responses.json"

# User-safe notices shown whenever a demo answer replaces a live LLM answer.
# They never contain secrets or provider error details.
DEMO_NOTICE = (
    "Demo fallback mode: the live Groq answer service is not configured or is "
    "currently unavailable, so this answer is a pre-made demo response and did "
    "not come from the Groq LLM. Add a valid GROQ_API_KEY and restart the API "
    "to enable live RAG answers."
)
DEMO_NOTICE_HI = (
    "डेमो फॉलबैक मोड: लाइव ग्रूक उत्तर सेवा कॉन्फ़िगर नहीं है या अभी उपलब्ध "
    "नहीं है, इसलिए यह उत्तर एक पहले से बनाया गया डेमो उत्तर है और ग्रूक एलएलएम "
    "से नहीं आया है। लाइव आरएजी उत्तर सक्षम करने के लिए एक मान्य GROQ_API_KEY "
    "जोड़ें और API को पुनः आरंभ करें।"
)

# Last-resort response when even the demo data file cannot be loaded. Contains
# no secrets and carries an empty source list, so /query still returns a valid
# response.
HARDCODED_FALLBACK_ANSWER = (
    "SchemeGPT is currently unable to produce an answer. The live Groq answer "
    "service is unavailable and the pre-made demo answers could not be loaded. "
    "Please try again later."
)
HARDCODED_FALLBACK_NOTICE = (
    "Demo fallback mode: the live Groq answer service is unavailable and the "
    "pre-made demo answers could not be loaded, so a generic response is shown."
)
HARDCODED_FALLBACK_ANSWER_HI = (
    "SchemeGPT इस समय उत्तर देने में असमर्थ है। लाइव ग्रूक उत्तर सेवा उपलब्ध "
    "नहीं है और पहले से बनाए गए डेमो उत्तर लोड नहीं किए जा सके। कृपया बाद में "
    "पुनः प्रयास करें।"
)
HARDCODED_FALLBACK_NOTICE_HI = (
    "डेमो फॉलबैक मोड: लाइव ग्रूक उत्तर सेवा उपलब्ध नहीं है और पहले से बनाए गए "
    "डेमो उत्तर लोड नहीं किए जा सके, इसलिए एक सामान्य उत्तर दिखाया गया है।"
)

# Safe short Hindi fallback used when a matching demo record has no ``answer_hi``
# translation, so a Hindi request never receives English text while being
# labelled as a Hindi answer.
HI_TRANSLATION_MISSING = (
    "इस प्रश्न का हिंदी उत्तर अभी उपलब्ध नहीं है। कृपया अंग्रेज़ी में पूछें या "
    "बाद में पुनः प्रयास करें।"
)

# --- Retrieval-only (degraded) answers ---------------------------------------
# Served when AI generation is unavailable: by operator decision (kill switch,
# POST /ops/ai) or because the provider is failing and the circuit breaker is
# open. These answers contain no generated text at all. The most relevant
# sentences are copied verbatim out of the retrieved source documents into the
# same "> <sentence> [<source>, <data_status>]" form the live prompt asks the
# model for, so the existing quote verifier proves them mechanically and the
# citizen can see exactly which document each line came from.
#
# Two rules this path holds to:
#   * It never pretends to be a synthesised answer: the notice says AI
#     generation is off and the text is excerpted from source documents.
#   * It is never written to the semantic cache, which stores live answers
#     only — a degraded answer must not be replayed later as a live one.
DEGRADED_NOTICE = (
    "Degraded mode: AI generation is disabled for this instance, so this "
    "answer was assembled directly from the retrieved source documents with "
    "no language model involved. The quoted lines are exact excerpts — read "
    "them as source material, not as a synthesised answer."
)
DEGRADED_NOTICE_HI = (
    "सीमित (डिग्रेडेड) मोड: इस इंस्टेंस पर एआई उत्तर-निर्माण बंद है, इसलिए यह "
    "उत्तर बिना किसी भाषा-मॉडल के, सीधे प्राप्त स्रोत दस्तावेज़ों से तैयार "
    "किया गया है। उद्धृत पंक्तियाँ स्रोत से ज्यों-की-त्यों ली गई हैं — इन्हें "
    "स्रोत सामग्री मानें, संश्लेषित उत्तर नहीं।"
)
DEGRADED_PREFACE = {
    "en": (
        "AI generation is currently off for this instance. These are the "
        "exact lines from the retrieved source documents that match your "
        "question:"
    ),
    "hi": (
        "इस इंस्टेंस पर एआई उत्तर-निर्माण अभी बंद है। आपके प्रश्न से मेल खाती "
        "स्रोत दस्तावेज़ों की मूल पंक्तियाँ ये हैं:"
    ),
}
DEGRADED_TAIL = {
    "en": (
        "No generated answer is available while AI generation is off. A "
        "synthesised answer returns as soon as an operator re-enables it "
        "(POST /ops/ai)."
    ),
    "hi": (
        "एआई उत्तर-निर्माण बंद रहने तक कोई संश्लेषित उत्तर उपलब्ध नहीं है। "
        "ऑपरेटर द्वारा इसे पुनः सक्षम करते ही संश्लेषित उत्तर लौट आएगा।"
    ),
}

MIN_SENTENCE_CHARS = 40
MAX_QUOTE_CHARS = 400
MAX_QUOTES = 3

# Split on sentence enders (Latin + Devanagari danda) and on blank lines.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+|\n\s*\n")
_TOKEN_RE = re.compile(r"[0-9a-z\u0900-\u097f]+")

# Deliberately tiny stopword list: question words that would otherwise match
# every sentence. Only used to rank *already retrieved* sentences.
_STOPWORDS = frozenset(
    """
    a an and are as at be been by can do does for from has have how i in is it
    its me my of on or should so that the their them there these this to was
    were what when where which who whom why will with you your
    """.split()
)


def _sentences(text: str) -> list[str]:
    """Split source text into candidate quotation sentences."""
    out: list[str] = []
    for raw in _SENTENCE_SPLIT_RE.split(text or ""):
        # Drop markdown structure and list/quote markers so a copied line
        # reads as a statement, not as formatting.
        cleaned = re.sub(r"^\s*(?:>|[-*+]|\d+[.)])\s*", "", raw).strip()
        cleaned = " ".join(cleaned.split())
        if cleaned:
            out.append(cleaned)
    return out


def _query_tokens(question: str) -> set[str]:
    tokens = {
        token
        for token in _TOKEN_RE.findall((question or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }
    return tokens or set(_TOKEN_RE.findall((question or "").lower()))


def _sentence_score(sentence: str, tokens: set[str]) -> int:
    if not tokens:
        return 0
    present = {token for token in tokens if token in sentence.lower()}
    return len(present)


def _shorten(sentence: str, limit: int = MAX_QUOTE_CHARS) -> str:
    """Cut a long sentence at a word boundary *without* adding punctuation.

    The cut stays a verbatim substring of the source, so containment-based
    quote verification still passes on it.
    """
    if len(sentence) <= limit:
        return sentence
    cut = sentence[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.strip()


def _doc_to_source(doc) -> dict:
    """Retrieved document -> the /query source shape (with provenance)."""
    return {
        "source": doc.metadata.get("source", ""),
        "content": doc.page_content,
        # `.get()` defaults keep old vectors (which lack these keys) working.
        "jurisdiction": doc.metadata.get("jurisdiction"),
        "state": doc.metadata.get("state"),
        "data_status": doc.metadata.get("data_status"),
        "last_verified": doc.metadata.get("last_verified"),
        "source_url": doc.metadata.get("source_url"),
    }


def _quote_lines(docs: list, question: str, max_quotes: int = MAX_QUOTES) -> list[str]:
    """Pick the best-matching sentence per document as a quote line.

    Ranking is deterministic: score by distinct query-token overlap, then keep
    document order (the retriever already ranked by relevance). Duplicate
    sentences across documents are kept once, from the first document that
    produced them.
    """
    tokens = _query_tokens(question)
    candidates: list[tuple[int, int, str, dict]] = []
    for doc_index, doc in enumerate(docs):
        best: tuple[int, int, str] | None = None
        for sent_index, sentence in enumerate(_sentences(doc.page_content)):
            if len(sentence) < MIN_SENTENCE_CHARS:
                continue
            if "[" in sentence and sentence.rstrip().endswith("]"):
                # Looks like a JSON/array fragment; a poor quotation.
                continue
            score = _sentence_score(sentence, tokens)
            key = (score, -sent_index)
            if best is None or key > best[:2]:
                best = (score, -sent_index, sentence)
        if best is not None:
            candidates.append((best[0], doc_index, best[2], _doc_to_source(doc)))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    lines: list[str] = []
    seen: set[str] = set()
    for _score_value, _doc_index, sentence, source in candidates:
        key = re.sub(r"[^0-9a-z\u0900-\u097f]+", " ", sentence.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        status = source.get("data_status")
        suffix = f"{source.get('source', '')}, {status}" if status else str(
            source.get("source", "")
        )
        lines.append(f"> {_shorten(sentence)} [{suffix}]")
        if len(lines) >= max_quotes:
            break
    return lines


def degraded_answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
    reason: str = "unavailable",
) -> dict:
    """Assemble a retrieval-only answer with verbatim, verifiable quotes.

    Retrieval only: no LLM call, no semantic-cache lookup or write. Raises
    ``Exception`` if retrieval itself fails; callers that must always return
    an HTTP 200 response should use :func:`fallback_answer` instead.
    """
    from app import metrics  # local import: metrics is a leaf module

    lang = _normalize_language(language)
    docs = get_retriever().invoke(question)
    sources = [_doc_to_source(doc) for doc in docs]
    lines = _quote_lines(list(docs), question)
    parts = [DEGRADED_PREFACE[lang]]
    if lines:
        parts.extend(lines)
    else:
        parts.append(
            "No matching lines were found in the indexed documents for this "
            "question."
            if lang == "en"
            else "इस प्रश्न के लिए अनुक्रमित दस्तावेज़ों में कोई मेल खाती पंक्ति नहीं मिली।"
        )
    parts.append(DEGRADED_TAIL[lang])
    metrics.inc("degraded_answers_total")
    logger.warning(
        "Serving retrieval-only answer (reason=%s, quotes=%d, sources=%d).",
        reason,
        len(lines),
        len(sources),
    )
    return {
        "answer": "\n\n".join(parts),
        "sources": sources,
        "mode": "degraded",
        "notice": DEGRADED_NOTICE_HI if lang == "hi" else DEGRADED_NOTICE,
        "language": lang,
    }


def fallback_answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
    reason: str = "unavailable",
) -> dict:
    """Prefer a retrieval-only answer; fall back to the pre-made demo answer.

    Used on every live-path failure so a provider or database problem degrades
    to something grounded instead of canned text — and still returns a valid
    response if retrieval is the thing that is broken.
    """
    try:
        return degraded_answer(question, language, profile, reason=reason)
    except Exception as exc:
        logger.error(
            "Retrieval-only fallback failed (%s); returning pre-made demo answer.",
            type(exc).__name__,
        )
        return demo_answer(question, language)


# Profile fields included in the compact profile context. ``display_name`` and
# ``language`` are deliberately excluded: they are not scheme-matching signals
# and excluding identity/derived fields shrinks the prompt-injection surface.
PROFILE_FIELD_LABELS_EN = (
    ("state", "state"),
    ("age", "age"),
    ("annual_income", "annual income"),
    ("occupation", "occupation"),
    ("social_category", "social category"),
    ("gender", "gender"),
    ("rural", "rural"),
    ("disability", "disability"),
    ("family_size", "family size"),
    ("goals", "goals"),
)
PROFILE_FIELD_LABELS_HI = (
    ("state", "राज्य"),
    ("age", "आयु"),
    ("annual_income", "वार्षिक आय"),
    ("occupation", "व्यवसाय"),
    ("social_category", "सामाजिक श्रेणी"),
    ("gender", "लिंग"),
    ("rural", "ग्रामीण"),
    ("disability", "विकलांगता"),
    ("family_size", "परिवार का आकार"),
    ("goals", "लक्ष्य"),
)


def _normalize_language(language: str | None) -> str:
    """Normalize a language value to ``"en"`` or ``"hi"`` (default ``"en"``)."""
    if language is not None and str(language).strip().lower() == "hi":
        return "hi"
    return "en"


def get_llm(role: str = "answer", max_tokens: int = 1024) -> ChatGroq:
    """Return a Groq ChatGroq instance for a task role.

    ``role="fast"`` uses the cheap fast model for small sub-tasks (question
    normalization, routing); ``"answer"``/``"agent"`` use the strong model for
    final answers and reasoning. ``max_tokens`` bounds every generation.
    """
    key = settings.groq_api_key
    if not key.strip():
        # Fail fast so no ChatGroq call is ever attempted without a key.
        raise ValueError(
            "GROQ_API_KEY is not set. Set a valid Groq API key to enable live "
            "RAG answers, or leave it blank to use the pre-made demo."
        )
    model = (
        settings.groq_fast_model if role == "fast" else settings.groq_model
    )
    if role == "judge" and settings.eval_judge_model.strip():
        model = settings.eval_judge_model.strip()
    # Optional endpoint override: route generation through the customer's API
    # gateway / egress proxy (GROQ_API_BASE) or a runtime override set by
    # POST /ops/provider. Empty means "use the client's default endpoint".
    base_url = operator.provider_base_url()
    extra = {"groq_api_base": base_url} if base_url else {}
    return ChatGroq(
        model=model,
        api_key=key,
        temperature=0,
        # Bound every live Groq generation so a public free-tier answer can
        # never consume unbounded output tokens. langchain-groq (pinned 0.3.5)
        # accepts this as a standard init arg.
        max_tokens=max_tokens,
        **extra,
    )


NORMALIZE_SYSTEM_PROMPT = (
    "You rewrite user questions about Indian government schemes into one clear, "
    "self-contained search query. The input may be broken English, Hindi, "
    "Hinglish, or colloquial phrasing. Preserve the original language and keep "
    "scheme names, acronyms, and numbers verbatim. Output ONLY the rewritten "
    "question - no preamble, no quotes, no explanation."
)


def normalize_question(question: str) -> str:
    """Rewrite a raw citizen question into a clean retrieval query.

    One cheap LLM call (fast model), temperature 0, tightly bounded. ANY
    failure (no key, API error, empty or oversized output) falls back to the
    raw question so retrieval always proceeds.
    """
    try:
        llm = get_llm("fast", max_tokens=160)
        resp = llm.invoke(
            [("system", NORMALIZE_SYSTEM_PROMPT), ("human", question)]
        )
        cleaned = str(resp.content).strip().strip('"').strip("'").strip()
        if not cleaned or len(cleaned) > 300:
            return question
        return cleaned
    except Exception as exc:
        logger.info(
            "Question normalization failed (%s); using raw question.",
            type(exc).__name__,
        )
        return question


@lru_cache
def _load_demo_responses() -> list[dict]:
    """Load and validate the pre-made demo responses (cached)."""
    raw = DEMO_RESPONSES_FILE.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("responses") or data.get("demo_responses") or []
    if not isinstance(data, list):
        raise ValueError("demo_responses.json must contain a JSON list of records")
    records = [
        item
        for item in data
        if isinstance(item, dict) and _record_answer_text(item) is not None
    ]
    if not records:
        raise ValueError("demo_responses.json contains no usable answer records")
    return records


def _record_answer_text(record: dict) -> str | None:
    """First usable answer text in a record (English or Hindi)."""
    for key in ("answer", "answer_hi"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation so keyword matching is whitespace-safe."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


@lru_cache
def _demo_source_metadata_lookup() -> dict[str, dict]:
    """Map a source basename to its catalog record for enriching demo sources."""
    lookup: dict[str, dict] = {}
    for record in load_scheme_catalog_records():
        source_file = str(record.get("source_file") or "")
        if not source_file:
            continue
        lookup.setdefault(Path(source_file).name, record)
    return lookup


def _demo_source(src: dict) -> dict:
    """Normalise a record's source to the schema, enriched with catalog metadata."""
    source_name = str(src.get("source", "") or "")
    base: dict = {
        "source": source_name,
        "content": src.get("content", ""),
        "jurisdiction": None,
        "state": None,
        "data_status": None,
        "last_verified": None,
        "source_url": None,
    }
    record = _demo_source_metadata_lookup().get(Path(source_name).name)
    if record:
        base["jurisdiction"] = record.get("jurisdiction")
        if record.get("type") in ("state", "union_territory"):
            base["state"] = record.get("name")
        base["data_status"] = record.get("data_status")
        base["last_verified"] = record.get("last_verified")
        base["source_url"] = record.get("source_url")
    return base


def _demo_sources(record: dict) -> list[dict]:
    """Normalise a record's sources to the schema with provenance metadata."""
    return [
        _demo_source(src)
        for src in record.get("sources") or []
        if isinstance(src, dict)
    ]


def demo_answer(question: str, language: str = "en") -> dict:
    """Return the best-matching pre-made demo answer in the requested language.

    Pure helper over the local JSON file: no database, no LLM, no API key.
    Returns a dict ready for ``QueryResponse`` with ``mode="demo"`` and the
    ``language`` normalized to ``"en"`` or ``"hi"``.
    """
    lang = _normalize_language(language)
    try:
        records = _load_demo_responses()
    except Exception:
        # Demo data itself failed to load; /query must still return a valid
        # response, so fall back to a hardcoded generic answer with no secrets
        # and an empty source list.
        logger.exception("Failed to load demo responses from %s", DEMO_RESPONSES_FILE)
        return {
            "answer": (
                HARDCODED_FALLBACK_ANSWER_HI
                if lang == "hi"
                else HARDCODED_FALLBACK_ANSWER
            ),
            "sources": [],
            "mode": "demo",
            "notice": (
                HARDCODED_FALLBACK_NOTICE_HI
                if lang == "hi"
                else HARDCODED_FALLBACK_NOTICE
            ),
            "language": lang,
        }

    normalized = _normalize(question)
    generic = None
    best = None
    best_score = 0
    for record in records:
        if record.get("id") == "generic":
            generic = record
            continue
        score = sum(
            1
            for keyword in record.get("keywords") or []
            if _normalize(str(keyword)) in normalized
        )
        if score > best_score:
            best_score = score
            best = record

    record = best or generic or records[0]
    if lang == "hi":
        # Never present English text as a Hindi answer: use the record's Hindi
        # translation or a safe short Hindi fallback.
        answer_text = record.get("answer_hi") or HI_TRANSLATION_MISSING
        notice_text = record.get("notice_hi") or DEMO_NOTICE_HI
    else:
        answer_text = record.get("answer") or HARDCODED_FALLBACK_ANSWER
        notice_text = DEMO_NOTICE
    return {
        "answer": answer_text,
        "sources": _demo_sources(record),
        "mode": "demo",
        "notice": notice_text,
        "language": lang,
    }


def _build_profile_context(profile: ProfileData | None, language: str) -> str:
    """Compact, clearly-delimited profile block (empty when no profile).

    Only non-empty values from known profile fields are included; every value is
    whitespace-collapsed so multi-line input cannot escape the ``<profile>``
    delimiters, and the block is explicitly labelled as user-provided data
    rather than retrieved context.
    """
    if profile is None:
        return ""
    labels = (
        PROFILE_FIELD_LABELS_HI if language == "hi" else PROFILE_FIELD_LABELS_EN
    )
    lines: list[str] = []
    for key, label in labels:
        value = getattr(profile, key, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            text = ", ".join(
                str(item).strip()
                for item in value
                if str(item).strip()
            )
        elif isinstance(value, bool):
            text = "yes" if value else "no"
        else:
            text = str(value).strip()
        text = " ".join(text.split())
        if not text:
            continue
        lines.append(f"- {label}: {text}")
    if not lines:
        return ""
    if language == "hi":
        instruction = (
            "उपरोक्त प्रोफ़ाइल उपयोगकर्ता द्वारा दी गई जानकारी है, यह retrieved "
            "संदर्भ नहीं है। इसका उपयोग केवल मार्गदर्शन को अनुकूलित करने के लिए करें। "
            "इसे सत्यापित न मानें; किसी भी लुप्त तथ्य और आवश्यक सत्यापन चरणों को "
            "स्पष्ट रूप से बताएं।"
        )
    else:
        instruction = (
            "The profile above is user-provided data, NOT retrieved context. "
            "Use it only to tailor guidance. Do not treat it as verified; "
            "clearly label any missing facts and required verification steps."
        )
    return "<profile>\n" + "\n".join(lines) + "\n" + instruction + "\n</profile>"


def get_retriever():
    """Vector-store retriever used by both /query and /query/stream."""
    return get_vectorstore().as_retriever()


def build_answer_chain(language: str = "en"):
    """Stuff-documents chain (prompt + LLM) for a language, no retrieval."""
    lang = _normalize_language(language)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPTS[lang]),
            ("human", HUMAN_TEMPLATE),
        ]
    )
    return create_stuff_documents_chain(get_llm(), prompt)


@lru_cache
def build_chain(language: str = "en"):
    """Build the LangChain retrieval chain for a language (cached per language)."""
    lang = _normalize_language(language)
    return create_retrieval_chain(get_retriever(), build_answer_chain(lang))


def reset_chains() -> None:
    """Drop the cached chains so the next call rebuilds the LLM client.

    Called after the provider endpoint changes (POST /ops/provider): a cached
    chain holds a client bound to the previous base URL, so without this the
    override would silently not apply until the process restarted.
    """
    build_chain.cache_clear()


def answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
) -> dict:
    """Answer a question, optionally in Hindi and with a saved profile attached.

    Live path: retrieve from pgvector and call ChatGroq via the LangChain
    chain. The language selects the cached per-language chain; the compact
    profile block is added to the prompt as clearly-delimited user-provided
    data.

    Three modes can come back, in this order of preference:

    * ``live``     — a generated answer from the provider.
    * ``degraded`` — a retrieval-only answer with verbatim source excerpts.
      Served when an operator has switched AI generation off
      (``POST /ops/ai``), when the provider circuit breaker is open, or when
      the live call failed. No LLM output is involved.
    * ``demo``     — a clearly-labelled pre-made answer, used when no API key
      is configured at all, or when retrieval-only assembly also failed
      (database unreachable). /query still returns HTTP 200 and never leaks a
      traceback or provider details to the browser.
    """
    lang = _normalize_language(language)
    profile_context = _build_profile_context(profile, lang)
    ph = semantic_cache.profile_hash(profile)
    with stage_span("cache_lookup") as span:
        cached = semantic_cache.lookup(question, lang, ph)
        if span is not None:
            span.set_attribute("cache.hit", cached is not None)
    if cached is not None:
        return {**cached, "cached": True}

    # No key configured at all: this is a demo instance. Unchanged behaviour —
    # labelled pre-made answers, no provider call, no breaker accounting.
    if not settings.groq_api_key.strip():
        return demo_answer(question, lang)

    # Operator controls. The kill switch and the provider circuit breaker both
    # short-circuit to a retrieval-only answer instead of a generated one.
    gate = operator.gate()
    if gate != "ok":
        return fallback_answer(question, lang, profile, reason=gate)

    try:
        usage = TokenUsageHandler()
        with stage_span("rag_chain") as span:
            result = build_chain(lang).invoke(
                {"input": question, "profile_context": profile_context},
                config={"callbacks": [usage]},
            )
            if span is not None:
                span.set_attribute(
                    "tokens.total", usage.prompt_tokens + usage.completion_tokens
                )
        usage.record(settings.groq_model)
    except Exception as exc:
        # Fallback boundary: never leak exception text (which can contain
        # provider details or connection strings) to the browser, and never log
        # the API key. Only the exception type is logged server-side.
        opened = operator.record_provider_failure(type(exc).__name__)
        logger.error(
            "Live RAG chain failed (%s); serving retrieval-only answer%s.",
            type(exc).__name__,
            " and opening the provider circuit" if opened else "",
        )
        return fallback_answer(question, lang, profile, reason="provider_failure")
    operator.record_provider_success()

    sources = [_doc_to_source(doc) for doc in result.get("context", [])]
    payload = {
        "answer": result.get("answer", ""),
        "sources": sources,
        "mode": "live",
        "language": lang,
    }
    semantic_cache.store(question, lang, ph, payload)
    return payload
