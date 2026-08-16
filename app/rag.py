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
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app.catalog import load_scheme_catalog_records
from app.config import ROOT_DIR, settings
from app.db import get_vectorstore
from app.schemas import ProfileData

logger = logging.getLogger(__name__)

# Per-language system prompts. The Hindi prompt (Devanagari) is natural and
# plain: answer only from context, keep scheme names/acronyms/amounts/URLs
# verbatim, state when information is unavailable, and never present a
# directory_seed record as a verified eligibility decision.
SYSTEM_PROMPTS = {
    "en": (
        "You are SchemeGPT, an assistant that answers questions about Indian "
        "government schemes and acts. Answer using only the provided context. "
        "If the answer is not in the context, say so. Treat any record whose "
        "data_status is 'directory_seed' as a discovery entry, never as a "
        "verified eligibility decision. Be concise and factual."
    ),
    "hi": (
        "आप SchemeGPT हैं, जो भारतीय सरकारी योजनाओं और अधिनियमों के बारे में "
        "सवालों के जवाब देने वाला सहायक है। केवल दिए गए संदर्भ (context) के आधार पर "
        "उत्तर दें। सरल और प्राकृतिक हिंदी में उत्तर दें। योजनाओं के नाम, संक्षिप्ताक्षर, "
        "राशियाँ/रकम और URL को मूल रूप में ही रखें। यदि जानकारी संदर्भ में उपलब्ध नहीं है, "
        "तो स्पष्ट रूप से कहें कि यह जानकारी उपलब्ध नहीं है। data_status 'directory_seed' "
        "वाली प्रविष्टि को कभी भी सत्यापित पात्रता निर्णय न बताएं — वह केवल एक "
        "खोज/डिस्कवरी प्रविष्टि है। संक्षिप्त और तथ्यात्मक रहें।"
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


def get_llm() -> ChatGroq:
    key = settings.groq_api_key
    if not key.strip():
        # Fail fast so no ChatGroq call is ever attempted without a key.
        raise ValueError(
            "GROQ_API_KEY is not set. Set a valid Groq API key to enable live "
            "RAG answers, or leave it blank to use the pre-made demo."
        )
    return ChatGroq(
        model=settings.groq_model,
        api_key=key,
        temperature=0,
        # Bound every live Groq generation so a public free-tier answer can
        # never consume unbounded output tokens. langchain-groq (pinned 0.3.5)
        # accepts this as a standard init arg.
        max_tokens=1024,
    )


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


def answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
) -> dict:
    """Answer a question, optionally in Hindi and with a saved profile attached.

    Live path: retrieve from pgvector and call ChatGroq via the LangChain
    chain. The language selects the cached per-language chain; the compact
    profile block is added to the prompt as clearly-delimited user-provided
    data. The live build/invoke path sits behind one exception boundary: any
    failure (missing/invalid/rate-limited Groq key, database or retrieval
    error, ordinary runtime/API exception) is converted into a clearly-labelled
    pre-made demo answer in the requested language so /query keeps returning
    HTTP 200. ``mode`` is ``"live"`` for live responses and ``"demo"`` with a
    localized notice for fallback.
    """
    lang = _normalize_language(language)
    profile_context = _build_profile_context(profile, lang)
    try:
        result = build_chain(lang).invoke(
            {"input": question, "profile_context": profile_context}
        )
    except Exception as exc:
        # Fallback boundary: never leak exception text (which can contain
        # provider details or connection strings) to the browser, and never log
        # the API key. Only the exception type is logged server-side.
        logger.error(
            "Live RAG chain failed (%s); returning pre-made demo answer.",
            type(exc).__name__,
        )
        return demo_answer(question, lang)

    sources = [
        {
            "source": doc.metadata.get("source", ""),
            "content": doc.page_content,
            # `.get()` defaults keep old vectors (which lack these keys) working.
            "jurisdiction": doc.metadata.get("jurisdiction"),
            "state": doc.metadata.get("state"),
            "data_status": doc.metadata.get("data_status"),
            "last_verified": doc.metadata.get("last_verified"),
            "source_url": doc.metadata.get("source_url"),
        }
        for doc in result.get("context", [])
    ]
    return {
        "answer": result.get("answer", ""),
        "sources": sources,
        "mode": "live",
        "language": lang,
    }
