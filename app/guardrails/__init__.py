"""PII guardrails: the pure, offline detection core (Phase 6a).

This package holds recognizers for Indian personal identifiers. It is
intentionally isolated from the request path: nothing here is wired into the
API, the vault, or the streaming pipeline yet (that is Phase 6b). Everything in
:mod:`app.guardrails.recognizers` is a pure function over text.

Import surface::

    from app.guardrails import Match, find_all
"""

from __future__ import annotations

from app.guardrails.recognizers import (
    KIND_AADHAAR,
    KIND_DEVANAGARI_DIGITS,
    KIND_GSTIN,
    KIND_IFSC,
    KIND_MOBILE,
    KIND_PAN,
    KIND_UPI,
    Match,
    find_all,
    is_aadhaar,
    recognize_aadhaar,
    recognize_devanagari_digits,
    recognize_gstin,
    recognize_ifsc,
    recognize_mobile,
    recognize_pan,
    recognize_upi,
    to_devanagari,
    verhoeff_check_digit,
    verhoeff_valid,
)

__all__ = [
    "KIND_AADHAAR",
    "KIND_DEVANAGARI_DIGITS",
    "KIND_GSTIN",
    "KIND_IFSC",
    "KIND_MOBILE",
    "KIND_PAN",
    "KIND_UPI",
    "Match",
    "find_all",
    "is_aadhaar",
    "recognize_aadhaar",
    "recognize_devanagari_digits",
    "recognize_gstin",
    "recognize_ifsc",
    "recognize_mobile",
    "recognize_pan",
    "recognize_upi",
    "to_devanagari",
    "verhoeff_check_digit",
    "verhoeff_valid",
]
