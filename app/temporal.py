"""Effective-dated claim extraction and "value in force on date T" resolution.

This corpus is a single snapshot: historical *documents* do not exist. What
exists is that a minority of documents **state their own history** -- a benefit
value that changed over time, each change carrying an effective date. The
versioning unit here is therefore an **effective-dated claim**, not a document
revision. Nothing is invented for a document that declares no history.

Boundary rule
-------------
``w.e.f. <date>`` (and its siblings ``with effect from``, ``effective from``,
``came into force``, and the bare ``from`` used by rate ladders) is
**inclusive**: on 2021-04-01 the new value applies; on 2021-03-31 the previous
value still applies. So :func:`resolve_as_of` returns the claim with the
greatest ``effective_from <= T``, and a claim takes over exactly on its own
date.

Never guess
-----------
A date with no value, or a value with no date, yields **no claim**. A value is
paired to the effective clause only when the value sits immediately before the
clause (within :data:`VALUE_LOOKBACK` characters), carries the ``/-`` rate
suffix, or is followed by a rate marker (``per month``, ``per annum``, ...).
A ladder whose distinct effective dates are not **strictly increasing in the
order they appear** is ambiguous and raises :class:`TemporalLadderError` rather
than being silently reordered. Equal dates are duplicates, not changes, and are
merged; that is what keeps ``01-04-2021`` / ``01.04.2021`` from becoming a
two-step chain.

Pattern set
-----------
Date spellings are normalised from an explicit, documented set:

* numeric ``dd.mm.yyyy`` / ``dd-mm-yyyy`` / ``dd/mm/yyyy`` (also ``d.m.yy``),
  read **day-first** (Indian order), matching every date in this corpus;
* ``<d>(st|nd|rd|th)? <Month> <yyyy>`` -- e.g. ``1st April, 2021``;
* ``<Month> <d>, <yyyy>`` -- e.g. ``April 1, 2019``;
* ``<Month> <yyyy>`` -- e.g. ``January 2014`` (day defaults to the 1st and the
  claim is marked ``date_confidence="month"``).

The module is pure: standard library only, no database, no network, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

VALUE_LOOKBACK = 80

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTH_WORD = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|"
    r"Nov|Dec)"
)

# A strong effective clause carries a date by itself.
STRONG_CLAUSES = (
    r"w\s*\.\s*e\s*\.\s*f\.?"
    r"|with\s+effect\s+from"
    r"|effective\s+from"
    r"|came\s+into\s+force"
    r"|came\s+into\s+effect"
)

# The bare "from" is only honoured by the ladder parser, and only when a value
# immediately precedes it (``... per month from January 2014``).
WEAK_CLAUSE = r"from"

_DATE_TOKEN = (
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_WORD + r"\.?,?\s+\d{4}"
    r"|" + _MONTH_WORD + r"\.?\s+\d{1,2},?\s+\d{4}"
    r"|" + _MONTH_WORD + r"\.?,?\s+\d{4}"
)

_STRONG_CLAUSE_RE = re.compile(
    r"(?P<clause>" + STRONG_CLAUSES + r")\s*[:\-]?\s*(?P<date>" + _DATE_TOKEN + r")",
    re.IGNORECASE,
)

_LADDER_CLAUSE_RE = re.compile(
    r"(?P<clause>" + STRONG_CLAUSES + r"|" + WEAK_CLAUSE + r")"
    r"\s*[:\-]?\s*(?P<date>" + _DATE_TOKEN + r")",
    re.IGNORECASE,
)

_VALUE_RE = re.compile(
    r"(?P<cur>₹|Rs\.?,?|INR)\s*(?P<num>\d[\d,]*(?:\.\d+)?)(?P<slash>\s*/-)?",
    re.IGNORECASE,
)

_RATE_MARKER_RE = re.compile(
    r"per\s+(?:month|annum|year|family|beneficiary|child|day)"
    r"|p\.?\s*m\.?\b"
    r"|p\.?\s*a\.?\b",
    re.IGNORECASE,
)

_MONTHLY_MARKER_RE = re.compile(r"per\s+month|p\.?\s*m\.?\b", re.IGNORECASE)

_ANNUAL_MARKER_RE = re.compile(r"per\s+annum|per\s+year|p\.?\s*a\.?\b", re.IGNORECASE)

_SPLIT_DATE_RE = re.compile(r"\d([ \t]*)([.\-])([ \t]*)\d")

_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$")
_DMY_RE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\.?,?\s+(\d{4})$",
    re.IGNORECASE,
)
_MDY_RE = re.compile(r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$", re.IGNORECASE)
_MY_RE = re.compile(r"^([A-Za-z]+)\.?,?\s+(\d{4})$", re.IGNORECASE)


class TemporalLadderError(ValueError):
    """A ladder is ambiguous: non-increasing dates or duplicate dates/values."""


@dataclass(frozen=True)
class DatedClaim:
    """One effective-dated value, tied verbatim to its source document."""

    claim_id: str
    value: int
    unit: str
    effective_from: date
    superseded_by: str | None
    source: str
    span: str
    date_confidence: str

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "value": self.value,
            "unit": self.unit,
            "effective_from": self.effective_from.isoformat(),
            "superseded_by": self.superseded_by,
            "source": self.source,
            "span": self.span,
            "date_confidence": self.date_confidence,
        }


def _flatten(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and repair a numeric date split across a line break.

    Returns the flattened string and, for every flattened character, its index
    in ``text``. The mapping lets a match on the flattened string be projected
    back onto the original text so the recorded ``span`` stays verbatim.
    """
    flat: list[str] = []
    origin: list[int] = []
    prev_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if prev_space:
                continue
            flat.append(" ")
            origin.append(index)
            prev_space = True
        else:
            flat.append(char)
            origin.append(index)
            prev_space = False
    joined = "".join(flat)
    drop = [False] * len(joined)
    for match in _SPLIT_DATE_RE.finditer(joined):
        for start, end in (
            (match.start(1), match.end(1)),
            (match.start(3), match.end(3)),
        ):
            for position in range(start, end):
                drop[position] = True
    if any(drop):
        joined = "".join(ch for i, ch in enumerate(joined) if not drop[i])
        origin = [o for i, o in enumerate(origin) if not drop[i]]
    return joined, origin


def _normalise_year(year: int) -> int:
    if year >= 100:
        return year
    return 1900 + year if year >= 50 else 2000 + year


def _parse_date_token(token: str) -> tuple[date, str] | None:
    """Parse one date token, returning ``(date, confidence)`` or ``None``.

    ``confidence`` is ``"day"`` when the day is explicit and ``"month"`` when
    only the month and year are given (day defaults to the 1st).
    """
    token = token.strip()
    match = _NUMERIC_DATE_RE.match(token)
    if match:
        day, month, year = (int(part) for part in match.groups())
        try:
            return date(_normalise_year(year), month, day), "day"
        except ValueError:
            return None
    match = _DMY_RE.match(token)
    if match:
        day = int(match.group(1))
        month = _MONTHS.get(match.group(2).casefold())
        if month is None:
            return None
        try:
            return date(int(match.group(3)), month, day), "day"
        except ValueError:
            return None
    match = _MDY_RE.match(token)
    if match:
        month = _MONTHS.get(match.group(1).casefold())
        if month is None:
            return None
        try:
            return date(int(match.group(3)), month, int(match.group(2))), "day"
        except ValueError:
            return None
    match = _MY_RE.match(token)
    if match:
        month = _MONTHS.get(match.group(1).casefold())
        if month is None:
            return None
        return date(int(match.group(2)), month, 1), "month"
    return None


def parse_effective_dates(text: str) -> list[date]:
    """Return every date carried by a *strong* effective clause, in order.

    Strong clauses are ``w.e.f.``, ``with effect from``, ``effective from``,
    ``came into force`` and ``came into effect``. The bare ``from`` used by
    rate ladders is intentionally excluded here: on its own it is too weak to
    call a date an effective date. Duplicates are preserved.
    """
    flat, _ = _flatten(text)
    found: list[date] = []
    for match in _STRONG_CLAUSE_RE.finditer(flat):
        parsed = _parse_date_token(match.group("date"))
        if parsed:
            found.append(parsed[0])
    return found


def _amount(raw: str) -> int:
    return int(raw.replace(",", "").split(".")[0])


def _unit_for(gap: str) -> str | None:
    if _ANNUAL_MARKER_RE.search(gap):
        return "INR/year"
    if _MONTHLY_MARKER_RE.search(gap):
        return "INR/month"
    return None


@dataclass
class _RawClaim:
    value: int
    effective_from: date
    date_confidence: str
    unit: str | None
    span: str
    order: int


def _extract_raw(text: str) -> list[_RawClaim]:
    flat, origin = _flatten(text)
    claims: list[_RawClaim] = []
    consumed: set[int] = set()
    for order, match in enumerate(_LADDER_CLAUSE_RE.finditer(flat)):
        clause = match.group("clause").casefold()
        if clause.startswith("from") and clause != "from":
            continue
        window_start = max(0, match.start() - VALUE_LOOKBACK)
        value_matches = [
            candidate
            for candidate in _VALUE_RE.finditer(flat, window_start, match.start())
            if candidate.start(1) not in consumed
        ]
        if not value_matches:
            continue
        value_match = value_matches[-1]
        gap = flat[value_match.end() : match.start()]
        if value_match.group("slash") is None and not _RATE_MARKER_RE.search(gap):
            continue
        parsed = _parse_date_token(match.group("date"))
        if parsed is None:
            continue
        effective_from, confidence = parsed
        consumed.add(value_match.start(1))
        span = text[
            origin[value_match.start()] : origin[match.end() - 1] + 1
        ]
        claims.append(
            _RawClaim(
                value=_amount(value_match.group("num")),
                effective_from=effective_from,
                date_confidence=confidence,
                unit=_unit_for(gap),
                span=span,
                order=order,
            )
        )
    return claims


def extract_claims(text: str, source: str) -> list[DatedClaim]:
    """Extract the effective-dated claims declared in one document.

    ``source`` is the document path recorded on every claim. Claims are
    de-duplicated by ``(value, effective_from)`` -- the same date written two
    ways is one claim, not two -- and must be **strictly increasing** by
    ``effective_from`` in the order they appear; otherwise
    :class:`TemporalLadderError` is raised. ``superseded_by`` links each claim
    to the next in the ladder and is ``None`` on the final claim.
    """
    raw = _extract_raw(text)
    seen: set[tuple[int, date]] = set()
    unique: list[_RawClaim] = []
    for claim in raw:
        key = (claim.value, claim.effective_from)
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)

    last_date: date | None = None
    for claim in unique:
        if last_date is not None and claim.effective_from <= last_date:
            raise TemporalLadderError(
                f"{source}: effective dates are not strictly increasing "
                f"({last_date.isoformat()} then "
                f"{claim.effective_from.isoformat()})"
            )
        last_date = claim.effective_from

    running_unit: str | None = None
    resolved: list[tuple[_RawClaim, str]] = []
    for claim in unique:
        if claim.unit is not None:
            running_unit = claim.unit
        resolved.append((claim, running_unit or "INR"))

    claims: list[DatedClaim] = []
    for index, (claim, unit) in enumerate(resolved):
        successor = (
            f"{source}#{resolved[index + 1][0].effective_from.isoformat()}"
            if index + 1 < len(resolved)
            else None
        )
        claims.append(
            DatedClaim(
                claim_id=f"{source}#{claim.effective_from.isoformat()}",
                value=claim.value,
                unit=unit,
                effective_from=claim.effective_from,
                superseded_by=successor,
                source=source,
                span=claim.span,
                date_confidence=claim.date_confidence,
            )
        )
    return claims


def resolve_as_of(claims: list[DatedClaim], as_of: date | str) -> DatedClaim | None:
    """Return the claim in force on ``as_of``, or ``None`` if the ladder starts later.

    The governing claim is the one with the greatest ``effective_from <= T``;
    the boundary is inclusive, so a claim governs on its own effective date.
    ``as_of`` may be a :class:`datetime.date` or an ISO ``YYYY-MM-DD`` string.
    """
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    governing = [claim for claim in claims if claim.effective_from <= as_of]
    if not governing:
        return None
    return max(governing, key=lambda claim: claim.effective_from)


def supersession_chain(
    claims: list[DatedClaim], claim_id: str
) -> list[DatedClaim]:
    """Walk forward from ``claim_id`` through ``superseded_by`` links.

    Returns the chain starting at the given claim and ending at the claim whose
    ``superseded_by`` is ``None``. A dangling or cyclic link raises
    :class:`TemporalLadderError`.
    """
    by_id = {claim.claim_id: claim for claim in claims}
    if claim_id not in by_id:
        raise KeyError(f"unknown claim_id: {claim_id}")
    chain: list[DatedClaim] = []
    seen: set[str] = set()
    current: DatedClaim | None = by_id[claim_id]
    while current is not None:
        if current.claim_id in seen:
            raise TemporalLadderError(
                f"supersession cycle at {current.claim_id}"
            )
        seen.add(current.claim_id)
        chain.append(current)
        if current.superseded_by is None:
            current = None
            continue
        successor = by_id.get(current.superseded_by)
        if successor is None:
            raise TemporalLadderError(
                f"{current.claim_id}: dangling superseded_by "
                f"{current.superseded_by!r}"
            )
        current = successor
    return chain


def claim_from_dict(record: dict) -> DatedClaim:
    """Rebuild a :class:`DatedClaim` from its JSONL fixture representation."""
    return DatedClaim(
        claim_id=str(record["claim_id"]),
        value=int(record["value"]),
        unit=str(record["unit"]),
        effective_from=date.fromisoformat(str(record["effective_from"])),
        superseded_by=record.get("superseded_by"),
        source=str(record["source"]),
        span=str(record["span"]),
        date_confidence=str(record["date_confidence"]),
    )
