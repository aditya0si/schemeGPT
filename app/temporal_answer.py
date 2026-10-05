"""Deterministic "what did this scheme say on <date>" answers.

When a ``/query`` request carries an ``as_of`` date, the answer must state the
value in force on that date, cite the verbatim span from the committed
dated-claims artifact, and name the replacement and the date it took over. This
module builds that answer from the frozen artifact -- it never re-extracts the
corpus at request time and never calls a language model.

Where the claims come from
--------------------------
``eval/fixtures/temporal_claims.jsonl``. It is the committed Task 1 artifact:
every record carries a verbatim ``span`` that a test proves literally appears in
its named source file, so a dated claim cannot be invented at request time. The
file is read **by path** (a data file); no ``eval`` module is imported.

Fail closed, never guess
------------------------
If the artifact is missing or unreadable, the question cannot be matched to a
single scheme ladder, or the requested date precedes the first declared value,
the answer says so explicitly. It NEVER falls back to the latest value while the
caller asked about a past date -- the one failure mode this whole feature exists
to prevent.
"""

from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.config import ROOT_DIR
from app.temporal import DatedClaim, claim_from_dict, resolve_as_of

# Response mode for every as-of payload (grounded or refused). Callers can
# distinguish an era-resolved answer from a live/degraded/demo one.
AS_OF_MODE = "as_of"

# The frozen, committed claims artifact (Task 1). Read by path, never imported.
FIXTURE_RELPATH = "eval/fixtures/temporal_claims.jsonl"

AS_OF_NOTICE = (
    "As-of answer: built deterministically from the committed dated-claims "
    "record (eval/fixtures/temporal_claims.jsonl). No language model was used, "
    "and no value from a different date was substituted."
)
AS_OF_REFUSAL_NOTICE = (
    "As-of answer refused: the value in force on the requested date could not "
    "be established from the committed dated-claims record. No current or "
    "latest value was substituted for the past date."
)
AS_OF_NOTICE_HI = (
    "तिथि-अनुसार उत्तर: यह प्रतिबद्ध दिनांकित-दावा रिकॉर्ड "
    "(eval/fixtures/temporal_claims.jsonl) से नियतात्मक रूप से बनाया गया है। "
    "कोई भाषा-मॉडल उपयोग नहीं हुआ, और किसी अन्य तिथि का मान प्रतिस्थापित नहीं किया गया।"
)
AS_OF_REFUSAL_NOTICE_HI = (
    "तिथि-अनुसार उत्तर अस्वीकृत: अनुरोधित तिथि पर लागू मान प्रतिबद्ध "
    "दिनांकित-दावा रिकॉर्ड से स्थापित नहीं हो सका। पिछली तिथि के लिए कोई "
    "वर्तमान या नवीनतम मान प्रतिस्थापित नहीं किया गया।"
)

_UNIT_WORDS = {"INR/month": "per month", "INR/year": "per year", "INR": ""}

# Title words that carry no scheme identity on their own, so a single one of
# them must not match a ladder. Everything else in an H1 title is distinctive.
_COMMON_TITLE_TOKENS = frozenset(
    """
    scheme schemes financial assistance allowance haryana pension state
    government department social security benefit benefits
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def claims_fixture_path() -> Path:
    """Absolute path to the committed dated-claims artifact."""
    return ROOT_DIR / "eval" / "fixtures" / "temporal_claims.jsonl"


@lru_cache(maxsize=4)
def _load_claims_from(path_str: str) -> tuple[DatedClaim, ...] | None:
    """Read the JSONL artifact into claims, or ``None`` if unusable.

    Any read/parse error degrades to ``None`` (the caller refuses); it never
    raises into the request path, so a missing or corrupt artifact cannot crash
    the server.
    """
    path = Path(path_str)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    claims: list[DatedClaim] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict) or record.get("type") == "header":
            continue
        try:
            claims.append(claim_from_dict(record))
        except (KeyError, TypeError, ValueError):
            return None
    return tuple(claims) if claims else None


def load_claims() -> tuple[DatedClaim, ...] | None:
    """Load the committed claims artifact, or ``None`` when unavailable."""
    return _load_claims_from(str(claims_fixture_path()))


@lru_cache(maxsize=64)
def _source_title(source: str) -> str:
    """The H1 title of a claim's source document, or its filename stem."""
    try:
        text = (ROOT_DIR / source).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Path(source).stem
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return Path(source).stem


def _aliases(source: str) -> tuple[str, set[str]]:
    """Return ``(filename_stem, distinctive_title_tokens)`` for matching."""
    stem = re.sub(r"[^a-z0-9]+", "", Path(source).stem.casefold())
    tokens = {
        token
        for token in _TOKEN_RE.findall(_source_title(source).casefold())
        if len(token) >= 4 and token not in _COMMON_TITLE_TOKENS
    }
    return stem, tokens


def match_scheme(
    question: str, claims: tuple[DatedClaim, ...]
) -> tuple[DatedClaim, ...] | None:
    """Return the single ladder the question names, or ``None``.

    A filename-stem hit (e.g. ``FADCS``) is decisive; otherwise distinctive H1
    title tokens vote. A tie between two ladders is ambiguous and returns
    ``None`` rather than guessing.
    """
    question_tokens = set(_TOKEN_RE.findall(question.casefold()))
    if not question_tokens:
        return None
    groups: dict[str, list[DatedClaim]] = {}
    for claim in claims:
        groups.setdefault(claim.source, []).append(claim)

    best_score = 0
    best_sources: list[str] = []
    for source in groups:
        stem, title_tokens = _aliases(source)
        score = 1000 if stem and stem in question_tokens else 0
        score += len(title_tokens & question_tokens)
        if score > best_score:
            best_score = score
            best_sources = [source]
        elif score == best_score and score > 0:
            best_sources.append(source)

    if best_score <= 0 or len(best_sources) != 1:
        return None
    ladder = sorted(groups[best_sources[0]], key=lambda claim: claim.effective_from)
    return tuple(ladder)


def _unit_phrase(unit: str) -> str:
    word = _UNIT_WORDS.get(unit)
    if word is None:
        word = unit.replace("INR/", "per ")
    return f" {word}" if word else ""


def _amount(claim: DatedClaim) -> str:
    return f"₹{claim.value:,}"


def _english_answer(
    as_of: date, claim: DatedClaim, successor: DatedClaim | None, title: str
) -> str:
    narrative = " ".join(
        [
            f"As of {as_of.isoformat()}, the value in force for {title} is "
            f"{_amount(claim)}{_unit_phrase(claim.unit)}.",
            f"It took effect on {claim.effective_from.isoformat()}.",
            (
                f"It remained in force until {successor.effective_from.isoformat()}, "
                f"when {_amount(successor)}{_unit_phrase(successor.unit)} took over."
                if successor is not None
                else "No later value is recorded; it is the most recent declared "
                "value in the committed claims."
            ),
        ]
    )
    return f'{narrative}\n\nSource: {claim.source} — "{claim.span}"'


def _hindi_answer(
    as_of: date, claim: DatedClaim, successor: DatedClaim | None, title: str
) -> str:
    narrative = " ".join(
        [
            f"{as_of.isoformat()} को {title} के लिए लागू मान "
            f"{_amount(claim)}{_unit_phrase(claim.unit)} है।",
            f"यह मान {claim.effective_from.isoformat()} से प्रभावी हुआ।",
            (
                f"यह {successor.effective_from.isoformat()} तक लागू रहा, जब "
                f"{_amount(successor)}{_unit_phrase(successor.unit)} ने इसे "
                f"प्रतिस्थापित किया।"
                if successor is not None
                else "कोई बाद का मान दर्ज नहीं है; यह प्रतिबद्ध दावों में सबसे "
                "नवीनतम घोषित मान है।"
            ),
        ]
    )
    return f'{narrative}\n\nस्रोत: {claim.source} — "{claim.span}"'


def _english_refusal(
    as_of: date,
    reason: str,
    title: str | None = None,
    earliest: DatedClaim | None = None,
) -> str:
    if reason == "missing":
        return (
            f"The committed dated-claims record is unavailable, so an as-of "
            f"answer for {as_of.isoformat()} cannot be established. No current "
            f"or latest value has been substituted for the requested date."
        )
    if reason == "unmatched":
        return (
            f"The question could not be matched to a scheme with a dated value "
            f"ladder, so an as-of answer for {as_of.isoformat()} cannot be "
            f"established. No current or latest value has been substituted for "
            f"the requested date."
        )
    assert earliest is not None
    return (
        f"No declared value is recorded for {title} on or before "
        f"{as_of.isoformat()}. The earliest declared value is "
        f"{_amount(earliest)}{_unit_phrase(earliest.unit)}, effective from "
        f"{earliest.effective_from.isoformat()}. The answer for this date cannot "
        f"be established, and no current or latest value has been substituted."
    )


def _hindi_refusal(
    as_of: date,
    reason: str,
    title: str | None = None,
    earliest: DatedClaim | None = None,
) -> str:
    if reason == "missing":
        return (
            f"प्रतिबद्ध दिनांकित-दावा रिकॉर्ड उपलब्ध नहीं है, इसलिए "
            f"{as_of.isoformat()} के लिए तिथि-अनुसार उत्तर स्थापित नहीं हो सकता। "
            f"अनुरोधित तिथि के लिए कोई वर्तमान या नवीनतम मान प्रतिस्थापित नहीं "
            f"किया गया।"
        )
    if reason == "unmatched":
        return (
            f"प्रश्न को दिनांकित मान-सीढ़ी वाली किसी योजना से मिलाया नहीं जा सका, "
            f"इसलिए {as_of.isoformat()} के लिए तिथि-अनुसार उत्तर स्थापित नहीं हो "
            f"सकता। अनुरोधित तिथि के लिए कोई वर्तमान या नवीनतम मान प्रतिस्थापित "
            f"नहीं किया गया।"
        )
    assert earliest is not None
    return (
        f"{title} के लिए {as_of.isoformat()} या उससे पहले कोई घोषित मान दर्ज नहीं "
        f"है। सबसे प्रारंभिक घोषित मान {_amount(earliest)}"
        f"{_unit_phrase(earliest.unit)} है, जो "
        f"{earliest.effective_from.isoformat()} से प्रभावी है। इस तिथि का उत्तर "
        f"स्थापित नहीं हो सकता; कोई वर्तमान या नवीनतम मान प्रतिस्थापित नहीं किया "
        f"गया।"
    )


def _source_entry(claim: DatedClaim) -> dict:
    return {
        "source": claim.source,
        "content": claim.span,
        "jurisdiction": None,
        "state": None,
        "data_status": None,
        "last_verified": None,
        "source_url": None,
    }


def _payload(
    answer_text: str, sources: list[dict], language: str, refused: bool
) -> dict:
    if language == "hi":
        notice = AS_OF_REFUSAL_NOTICE_HI if refused else AS_OF_NOTICE_HI
    else:
        notice = AS_OF_REFUSAL_NOTICE if refused else AS_OF_NOTICE
    return {
        "answer": answer_text,
        "sources": sources,
        "quotes": [],
        "steps": [],
        "mode": AS_OF_MODE,
        "notice": notice,
        "language": language,
    }


def temporal_answer(
    question: str, as_of: date | str, language: str = "en"
) -> dict:
    """Build the as-of payload for ``question`` at ``as_of``.

    Returns the normal ``/query`` payload shape (``answer``, ``sources``,
    ``mode="as_of"``, ``notice``, ``language``) plus empty ``quotes``/``steps``.
    Refusals carry the same shape with an explanatory answer and no sources.
    """
    as_of_date = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    lang = "hi" if str(language).strip().lower() == "hi" else "en"
    refuse = _hindi_refusal if lang == "hi" else _english_refusal

    claims = load_claims()
    if claims is None:
        return _payload(refuse(as_of_date, "missing"), [], lang, refused=True)

    ladder = match_scheme(question, claims)
    if ladder is None:
        return _payload(refuse(as_of_date, "unmatched"), [], lang, refused=True)

    governing = resolve_as_of(list(ladder), as_of_date)
    if governing is None:
        earliest = min(ladder, key=lambda claim: claim.effective_from)
        text = refuse(
            as_of_date,
            "before",
            title=_source_title(earliest.source),
            earliest=earliest,
        )
        return _payload(text, [], lang, refused=True)

    by_id = {claim.claim_id: claim for claim in ladder}
    successor = (
        by_id.get(governing.superseded_by) if governing.superseded_by else None
    )
    title = _source_title(governing.source)
    build = _hindi_answer if lang == "hi" else _english_answer
    return _payload(
        build(as_of_date, governing, successor, title),
        [_source_entry(governing)],
        lang,
        refused=False,
    )
