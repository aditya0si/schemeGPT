"""Deterministic, Groq-free starter recommendations built from the local catalog.

Iteration 1: no LLM is called. Central sample schemes are ranked with simple,
explainable profile signals (age, income, occupation, goals, rural). The
matching state/Union Territory directory seed is appended for the citizen's
state. Directory seeds are never presented as verified eligibility decisions:
every response carries a clear disclaimer and each item exposes its
``data_status`` and ``last_verified``.

Iteration 2: when ``language="hi"`` the deterministic output is localized to
plain Hindi using a small explicit translation/template map built from the
existing catalog metadata. No Groq call is made for ranking or translation, and
no state scheme facts are invented. State directory items say - in Hindi - that
they are discovery entries, not verified eligibility decisions.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.catalog import (
    load_scheme_catalog_records,
    load_states_by_name,
    normalize_name,
    slugify,
)
from app.config import ROOT_DIR
from app.schemas import (
    ProfileData,
    RecommendationItem,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)

MAX_CENTRAL_RECOMMENDATIONS = 4

DISCLAIMER = (
    "These are starter recommendations from SchemeGPT's discovery catalog. "
    "Central schemes are matched by simple profile signals and are sample "
    "records (data_status: sample_verified). State/Union Territory entries are "
    "discovery/coverage seeds (data_status: directory_seed): they are not "
    "verified eligibility decisions. Always verify scheme-level eligibility "
    "against the official national MyScheme discovery portal "
    "(https://www.myscheme.gov.in/) and the scheme's issuing department "
    "before applying."
)

DISCLAIMER_HI = (
    "ये SchemeGPT की डिस्कवरी कैटलॉग से प्रारंभिक अनुशंसाएँ हैं। केंद्रीय योजनाएँ "
    "सरल प्रोफ़ाइल संकेतों द्वारा मिलाई जाती हैं और नमूना रिकॉर्ड हैं "
    "(data_status: sample_verified)। राज्य/केंद्र शासित प्रदेश प्रविष्टियाँ "
    "डिस्कवरी/कवरेज सीड हैं (data_status: directory_seed): ये सत्यापित पात्रता "
    "निर्णय नहीं हैं। आवेदन से पहले हमेशा योजना-स्तरीय पात्रता आधिकारिक राष्ट्रीय "
    "MyScheme डिस्कवरी पोर्टल (https://www.myscheme.gov.in/) और संबंधित विभाग "
    "से सत्यापित करें।"
)

CATEGORIES_LABEL = (
    "income support, health, education, housing, jobs, agriculture, social security"
)
CATEGORIES_LABEL_HI = "आय सहायता, स्वास्थ्य, शिक्षा, आवास, नौकरियाँ, कृषि, सामाजिक सुरक्षा"

# Reason tags produced by ``_score_central_scheme`` mapped to plain Hindi.
REASON_TAGS_HI = {
    "matches occupation": "व्यवसाय से मेल खाता है",
    "matches selected goals": "चुने गए लक्ष्यों से मेल खाता है",
    "within documented age band": "दस्तावेजित आयु सीमा के भीतर",
    "within documented income cap": "दस्तावेजित आय सीमा के भीतर",
    "general relevance": "सामान्य प्रासंगिकता",
}

# Explicit Hindi scope/benefit lines for the existing central sample schemes,
# mirroring the facts in data/schemes/*.md. Never invented beyond that source.
HI_CENTRAL_BENEFITS = {
    "pm-kisan": (
        "पात्र भूमिधारी किसान परिवारों को प्रति वर्ष ₹6,000 की आय सहायता, तीन "
        "समान किश्तों में डीबीटी द्वारा सीधे बैंक खाते में।"
    ),
    "ayushman-bharat": (
        "प्रति परिवार प्रति वर्ष ₹5 लाख तक का स्वास्थ्य कवर, फ्लोटर आधार पर, "
        "माध्यमिक और तृतीयक अस्पताल में भर्ती के लिए।"
    ),
    "pmay-g": (
        "मैदानी क्षेत्रों में ₹1.20 लाख और पहाड़ी/कठिन/आईएपी क्षेत्रों में ₹1.30 "
        "लाख की सहायता से बुनियादी सुविधाओं वाला पक्का मकान।"
    ),
    "pm-sym": (
        "60 वर्ष की आयु के बाद प्रति माह ₹3,000 की पेंशन; प्रवेश आयु 18-40 वर्ष, "
        "मासिक योगदान ₹55-₹200, केंद्र सरकार बराबर का योगदान।"
    ),
    "startup-india": (
        "डीपीआईआईटी मान्यता पर पहले 10 वर्षों में से 3 वर्षों के मुनाफे पर 100% "
        "आयकर छूट और एंजेल टैक्स से छूट।"
    ),
    "gst": (
        "1 जुलाई 2017 से लागू; वस्तुओं के लिए ₹40 लाख और सेवाओं के लिए ₹20 लाख "
        "टर्नओवर पर पंजीकरण; मुख्य स्लैब 5%, 12%, 18%, 28%।"
    ),
}
# Safe, factual Hindi fallback for a central scheme without a translated line.
HI_SCOPE_FALLBACK = "विवरण के लिए स्रोत दस्तावेज़ देखें।"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _normalize_language(language: str | None) -> str:
    if language is not None and str(language).strip().lower() == "hi":
        return "hi"
    return "en"


@lru_cache
def _first_paragraph(path: Path) -> str:
    """First non-heading paragraph of a Markdown doc (a concise scope line)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Could not read %s for a scope line", path)
        return ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return ""


def _overlap_count(values_a: list[str], values_b: list[str]) -> int:
    normalized_a = {_normalize(value) for value in values_a if str(value).strip()}
    normalized_b = {_normalize(value) for value in values_b if str(value).strip()}
    return len(normalized_a & normalized_b)


def _score_central_scheme(record: dict, profile: ProfileData) -> tuple[int, list[str]]:
    """Explainable match score; a score > 0 means the scheme is worth showing."""
    score = 0
    reasons: list[str] = []

    occupation = _normalize(profile.occupation or "")
    occupations = [_normalize(value) for value in record.get("occupations") or []]
    if occupation and occupations:
        for target in occupations:
            if occupation == target or occupation in target or target in occupation:
                score += 3
                reasons.append("matches occupation")
                break

    matched_goals = _overlap_count(profile.goals or [], record.get("tags") or [])
    if matched_goals:
        score += 2 * matched_goals
        reasons.append("matches selected goals")

    age = profile.age
    min_age = record.get("min_age")
    max_age = record.get("max_age")
    if age is not None:
        if min_age is not None and age < min_age:
            score -= 4
        elif max_age is not None and age > max_age:
            score -= 4
        elif min_age is not None or max_age is not None:
            score += 1
            reasons.append("within documented age band")

    income = profile.annual_income
    income_max = record.get("income_max")
    if income is not None and income_max is not None:
        if income > income_max:
            score -= 4
        else:
            score += 1
            reasons.append("within documented income cap")

    # A rural-only scheme (e.g. PMAY-G) does not match an explicitly urban profile.
    if record.get("rural") is True and profile.rural is False:
        score -= 4

    return score, reasons


@lru_cache
def _state_catalog_by_name() -> dict[str, dict]:
    """Scheme-catalog records for state/UT directory seeds, keyed by normalized name.

    Keys use the same punctuation-insensitive rule as the states catalog lookup
    (``app.catalog.normalize_name``), so ``"Delhi (NCT)"`` and a profile's
    ``"Delhi NCT"`` resolve the same record.
    """
    lookup: dict[str, dict] = {}
    for record in load_scheme_catalog_records():
        if record.get("jurisdiction") == "central":
            continue
        name = str(record.get("name") or "")
        normalized = normalize_name(name)
        if normalized:
            lookup[normalized] = record
    return lookup


def _state_directory_item(record: dict, language: str) -> RecommendationItem:
    name = str(record.get("name") or "")
    data_status = str(record.get("data_status") or "directory_seed")
    source = record.get("source_file") or ""
    if not source:
        # Defensive fallback for a states-catalog-only record: use the same
        # slug rule as the data/states/ filenames (e.g. "Delhi (NCT)" ->
        # data/states/delhi-nct.md).
        slug = slugify(str(record.get("name") or ""))
        source = f"data/states/{slug}.md"
    source_url = record.get("source_url") or record.get("discovery_url") or ""
    if language == "hi":
        reason = (
            f"{name} के लिए डिस्कवरी/कवरेज प्रविष्टि: इस क्षेत्र में उपलब्ध "
            "योजनाओं की खोज यहीं से शुरू करें। यह एक डिस्कवरी प्रविष्टि है, "
            "सत्यापित पात्रता निर्णय नहीं।"
        )
        scope = (
            f"डिस्कवरी/कवरेज प्रविष्टि ({data_status})। खोजने योग्य श्रेणियाँ: "
            f"{CATEGORIES_LABEL_HI}।"
        )
        if source_url:
            scope += f" आधिकारिक राष्ट्रीय डिस्कवरी पोर्टल: {source_url}"
    else:
        reason = (
            f"Directory seed for {name}: start here to explore schemes "
            "available in this jurisdiction."
        )
        scope = (
            f"Discovery/coverage seed ({data_status}). Categories to explore: "
            f"{CATEGORIES_LABEL}."
        )
        if source_url:
            scope += f" Official national discovery portal: {source_url}"
    return RecommendationItem(
        id=str(record.get("id") or ""),
        name=name,
        jurisdiction=name,
        reason=reason,
        benefits_or_scope=scope,
        source=source,
        data_status=data_status,
        last_verified=record.get("last_verified"),
        source_url=source_url or None,
    )


def build_recommendations(
    profile: ProfileData, language: str = "en"
) -> RecommendationResponse:
    """Return deterministic starter recommendations for a profile.

    No Groq/LLM call is made. Central schemes are ranked with simple profile
    signals; the state/UT directory seed for ``profile.state`` is appended when
    one is selected. No state-specific match is fabricated otherwise. When
    ``language="hi"``, ``reason``/``benefits_or_scope`` and the disclaimer are
    returned in plain Hindi via the explicit translation/template map above.
    """
    lang = _normalize_language(language)
    items: list[RecommendationItem] = []

    scored: list[tuple[int, dict, list[str]]] = []
    for record in load_scheme_catalog_records():
        if record.get("jurisdiction") != "central":
            continue
        if record.get("data_status") != "sample_verified":
            continue
        score, reasons = _score_central_scheme(record, profile)
        if score > 0:
            scored.append((score, record, reasons))
    # Highest score first; deterministic tie-break by id.
    scored.sort(key=lambda entry: (-entry[0], str(entry[1].get("id", ""))))

    for _, record, reasons in scored[:MAX_CENTRAL_RECOMMENDATIONS]:
        scheme_id = str(record.get("id", ""))
        if lang == "hi":
            translated = [
                REASON_TAGS_HI.get(reason_tag, reason_tag)
                for reason_tag in (reasons or ["general relevance"])
            ]
            reason_text = "मिलान के आधार: " + ", ".join(translated) + "।"
            scope = HI_CENTRAL_BENEFITS.get(scheme_id) or HI_SCOPE_FALLBACK
        else:
            reason_text = ", ".join(reasons) if reasons else "general relevance"
            reason_text = f"Matched on: {reason_text}."
            scope = _first_paragraph(ROOT_DIR / record["source_file"])
            scope = scope or "See the source document for details."
        items.append(
            RecommendationItem(
                id=scheme_id,
                name=str(record.get("name", "")),
                jurisdiction="central",
                reason=reason_text,
                benefits_or_scope=scope,
                source=str(record.get("source_file", "")),
                data_status=str(record.get("data_status", "")),
                last_verified=record.get("last_verified"),
                source_url=record.get("source_url") or None,
            )
        )

    profile_state = None
    state_text = _normalize(profile.state or "")
    if state_text:
        state_record = load_states_by_name().get(state_text)
        if state_record:
            # The exact catalog name is preserved in responses (never the
            # normalized key), so "Delhi (NCT)" is returned for "Delhi NCT".
            profile_state = state_record.get("name")
            catalog_record = _state_catalog_by_name().get(
                normalize_name(profile_state)
            )
            items.append(
                _state_directory_item(catalog_record or state_record, lang)
            )

    return RecommendationResponse(
        recommendations=items,
        disclaimer=DISCLAIMER_HI if lang == "hi" else DISCLAIMER,
        profile_state=profile_state,
    )
