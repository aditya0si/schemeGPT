"""PII guardrails: the offline detection core and its reversible vault (6b).

This package holds recognizers for Indian personal identifiers and the
request-scoped vault that can hide them from a hosted provider and put them back
afterwards. The recognizers are pure functions over text; the vault is
in-memory only and never persisted, logged, or returned (see
:mod:`app.guardrails.vault`).

Import surface::

    from app.guardrails import Match, find_all, Vault
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
from app.guardrails.vault import Vault, restore, tokenize

__all__ = [
    "KIND_AADHAAR",
    "KIND_DEVANAGARI_DIGITS",
    "KIND_GSTIN",
    "KIND_IFSC",
    "KIND_MOBILE",
    "KIND_PAN",
    "KIND_UPI",
    "Match",
    "Vault",
    "find_all",
    "is_aadhaar",
    "recognize_aadhaar",
    "recognize_devanagari_digits",
    "recognize_gstin",
    "recognize_ifsc",
    "recognize_mobile",
    "recognize_pan",
    "recognize_upi",
    "restore",
    "to_devanagari",
    "tokenize",
    "verhoeff_check_digit",
    "verhoeff_valid",
]
