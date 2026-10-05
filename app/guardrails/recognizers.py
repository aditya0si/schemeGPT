"""Pure, offline PII recognizers for Indian identifiers.

This is the detection core of the sovereign/offline-first PII layer. It is
deliberately dependency-free and side-effect-free:

* pure functions only -- no I/O, no network, no database, no logging;
* no third-party dependency (the Verhoeff checksum is implemented here);
* importable in a process that has no database or provider client.

``find_all(text)`` runs every recognizer and resolves overlaps with a
deterministic rule (below). Each recognizer is also exported on its own so it
can be tested and reasoned about in isolation.

Overlap-resolution rule
-----------------------
Candidates from every recognizer are sorted by ``(start, -length, priority,
kind)`` and walked left to right. A candidate is accepted when its ``start`` is
at or after the end of the last accepted match (``start >= last_end``);
otherwise it is discarded. In words: **the leftmost match wins; among matches
that begin at the same offset the longest wins; any later match that overlaps an
already-accepted span is dropped.** The fixed ``priority`` order only breaks
exact ties on ``(start, length)`` and prefers the more specific kind:

    gstin > aadhaar > pan > ifsc > upi > mobile > devanagari_digits

Two consequences are load-bearing and tested explicitly:

* A GSTIN contains a PAN, so the PAN recognizer (which is intentionally not
  anchored against adjacent digits) also fires inside it. The GSTIN starts
  earlier, is accepted first, and its inner PAN is discarded. A standalone PAN
  is still reported.
* Every digit-based recognizer is boundary-anchored with ``(?<!\\d)`` /
  ``(?!\\d)`` (on the digit-normalised text), so a 12-digit Aadhaar embedded in
  a longer digit run is *not* a standalone Aadhaar and is not reported.

Devanagari digits
-----------------
Indian identifiers are frequently written in Devanagari numerals
(``०१२३४५६७८९``). Numeric recognizers run over a normalised copy of the text in
which each Devanagari digit is replaced by its ASCII equivalent, then map the
match coordinates back to the original string so the reported span covers the
*original* Devanagari characters. ``recognize_devanagari_digits`` additionally
reports any standalone run of Devanagari digits as its own generic kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KIND_AADHAAR = "aadhaar"
KIND_PAN = "pan"
KIND_GSTIN = "gstin"
KIND_IFSC = "ifsc"
KIND_UPI = "upi"
KIND_MOBILE = "mobile"
KIND_DEVANAGARI_DIGITS = "devanagari_digits"

# Lower value wins an exact (start, length) tie.
KIND_PRIORITY = {
    KIND_GSTIN: 0,
    KIND_AADHAAR: 1,
    KIND_PAN: 2,
    KIND_IFSC: 3,
    KIND_UPI: 4,
    KIND_MOBILE: 5,
    KIND_DEVANAGARI_DIGITS: 6,
}

DEVANAGARI_DIGITS = "\u0966\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u096e\u096f"
_DEVANAGARI_TO_ASCII = {
    ord(digit): str(index) for index, digit in enumerate(DEVANAGARI_DIGITS)
}
_ASCII_TO_DEVANAGARI = {
    str(index): digit for index, digit in enumerate(DEVANAGARI_DIGITS)
}

# Devanagari digit block (U+0966..U+096F).
_DEVANAGARI_RUN_RE = re.compile("[\u0966-\u096f]{4,}")
_ASCII_DIGIT_RE = re.compile(r"[0-9]")

# Aadhaar: 12 digits, contiguous or in 4-4-4 groupings separated by a single
# space or hyphen. Boundary-anchored so it cannot match inside a longer run.
_AADHAAR_RE = re.compile(
    r"(?<!\d)(?:\d{12}|\d{4}[ -]\d{4}[ -]\d{4})(?!\d)"
)

# PAN is deliberately *not* boundary-anchored against digits, so the inner PAN
# of a GSTIN is produced as a candidate and the overlap rule removes it.
_PAN_RE = re.compile(r"(?<![A-Z])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z])")

_GSTIN_RE = re.compile(
    r"(?<![0-9A-Z])[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}(?![0-9A-Z])"
)

_IFSC_RE = re.compile(r"(?<![0-9A-Z])[A-Z]{4}0[A-Z0-9]{6}(?![0-9A-Z])")

# local@handle. The local part may contain . _ -; the handle is letters/digits
# with no dot, and the trailing lookahead rejects a dotted domain so an email
# is not reported as a UPI id.
_UPI_RE = re.compile(
    r"(?<![A-Za-z0-9._-])[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z][A-Za-z0-9]{2,}(?![A-Za-z0-9.])"
)

# Indian mobile: optional +91 (with an optional space/hyphen) then 10 digits
# beginning 6-9. Boundary-anchored so it cannot match inside a longer run.
_MOBILE_RE = re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)")


@dataclass(frozen=True)
class Match:
    """One detected PII span in the original text."""

    start: int
    end: int
    kind: str
    text: str


# --------------------------------------------------------------------------
# Verhoeff checksum (pure Python; no dependency)
# --------------------------------------------------------------------------

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def normalize_digits(text: str) -> str:
    """Return ``text`` with Devanagari digits rewritten to ASCII digits.

    Both encodings are one code point per digit, so the character at index ``i``
    of the result corresponds to the character at index ``i`` of the original;
    callers can map match coordinates back without a separate index table.
    """
    return text.translate(_DEVANAGARI_TO_ASCII)


def to_devanagari(value: str) -> str:
    """Rewrite ASCII digit characters in ``value`` to Devanagari numerals."""
    return value.translate(_ASCII_TO_DEVANAGARI)


def digits_only(value: str) -> str:
    """Return only the ASCII digits of ``value`` (Devanagari normalised first)."""
    return "".join(_ASCII_DIGIT_RE.findall(normalize_digits(value)))


def verhoeff_valid(value: str) -> bool:
    """True when ``value``'s digits carry a valid Verhoeff check digit.

    Non-digit characters are ignored. Returns ``False`` for an empty string.
    """
    digits = digits_only(value)
    if not digits:
        return False
    checksum = 0
    for index, char in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[index % 8][int(char)]]
    return checksum == 0


def verhoeff_check_digit(digits: str) -> int:
    """Return the Verhoeff check digit for ``digits`` (the payload digits)."""
    payload = digits_only(digits)
    checksum = 0
    for index, char in enumerate(reversed(payload)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[(index + 1) % 8][int(char)]]
    return _VERHOEFF_INV[checksum]


def is_aadhaar(value: str) -> bool:
    """True when ``value`` is exactly 12 digits with a valid Verhoeff checksum."""
    return len(digits_only(value)) == 12 and verhoeff_valid(value)


# --------------------------------------------------------------------------
# Recognizers
# --------------------------------------------------------------------------


def _spans_from_normalized(pattern: re.Pattern[str], text: str) -> list[tuple[int, int]]:
    """Find ``pattern`` on the digit-normalised text, mapping back to ``text``.

    Because Devanagari and ASCII digits are both one code point long, the
    normalised and original coordinates coincide; the normalisation is what
    makes a Devanagari-written identifier match an ASCII pattern.
    """
    normalized = normalize_digits(text)
    return [(m.start(), m.end()) for m in pattern.finditer(normalized)]


def recognize_aadhaar(text: str) -> list[Match]:
    """12-digit Aadhaar numbers, tolerating 4-4-4 space/hyphen groupings."""
    matches: list[Match] = []
    for start, end in _spans_from_normalized(_AADHAAR_RE, text):
        if is_aadhaar(text[start:end]):
            matches.append(Match(start, end, KIND_AADHAAR, text[start:end]))
    return matches


def recognize_pan(text: str) -> list[Match]:
    """PAN in ``[A-Z]{5}[0-9]{4}[A-Z]`` form (may fire inside a GSTIN)."""
    return [
        Match(m.start(), m.end(), KIND_PAN, m.group(0))
        for m in _PAN_RE.finditer(text)
    ]


def recognize_gstin(text: str) -> list[Match]:
    """15-character GSTIN numbers."""
    return [
        Match(m.start(), m.end(), KIND_GSTIN, m.group(0))
        for m in _GSTIN_RE.finditer(text)
    ]


def recognize_ifsc(text: str) -> list[Match]:
    """IFSC bank/branch codes in ``[A-Z]{4}0[A-Z0-9]{6}`` form."""
    return [
        Match(m.start(), m.end(), KIND_IFSC, m.group(0))
        for m in _IFSC_RE.finditer(text)
    ]


def recognize_upi(text: str) -> list[Match]:
    """UPI ids in ``local@handle`` form."""
    return [
        Match(m.start(), m.end(), KIND_UPI, m.group(0))
        for m in _UPI_RE.finditer(text)
    ]


def recognize_mobile(text: str) -> list[Match]:
    """Indian mobile numbers, with or without a ``+91`` prefix."""
    return [
        Match(start, end, KIND_MOBILE, text[start:end])
        for start, end in _spans_from_normalized(_MOBILE_RE, text)
    ]


def recognize_devanagari_digits(text: str) -> list[Match]:
    """Standalone runs of four or more Devanagari digits, original span."""
    return [
        Match(m.start(), m.end(), KIND_DEVANAGARI_DIGITS, m.group(0))
        for m in _DEVANAGARI_RUN_RE.finditer(text)
    ]


RECOGNIZERS = (
    recognize_gstin,
    recognize_aadhaar,
    recognize_pan,
    recognize_ifsc,
    recognize_upi,
    recognize_mobile,
    recognize_devanagari_digits,
)


def find_all(text: str) -> list[Match]:
    """Run every recognizer over ``text`` and resolve overlaps deterministically.

    See the module docstring for the exact rule. The returned list is ordered by
    ``(start, end)`` and contains no two overlapping matches.
    """
    candidates: list[Match] = []
    for recognizer in RECOGNIZERS:
        candidates.extend(recognizer(text))

    candidates.sort(
        key=lambda match: (
            match.start,
            -(match.end - match.start),
            KIND_PRIORITY[match.kind],
            match.kind,
        )
    )

    accepted: list[Match] = []
    last_end = -1
    for candidate in candidates:
        if candidate.start >= last_end:
            accepted.append(candidate)
            last_end = candidate.end
    return accepted
