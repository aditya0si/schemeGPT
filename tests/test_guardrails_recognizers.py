"""Guardrail recognizer tests: pure, offline, no database required.

Covers each recognizer's positive and negative cases, the Verhoeff checksum
against known-good and known-bad values, the deterministic overlap rule
(GSTIN/PAN containment and Aadhaar-in-a-longer-run), Devanagari digit handling,
and ``find_all`` determinism.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.guardrails import (
    KIND_AADHAAR,
    KIND_DEVANAGARI_DIGITS,
    KIND_GSTIN,
    KIND_IFSC,
    KIND_MOBILE,
    KIND_PAN,
    KIND_UPI,
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

ROOT = Path(__file__).resolve().parent.parent

# Known-good from the canonical Verhoeff worked example (236 -> check digit 3)
# and dummy Aadhaar numbers used in public test suites.
KNOWN_VALID = ("2363", "999941057058", "234123412346")
KNOWN_INVALID = ("2364", "2362", "123456789012", "999941057059")

VALID_AADHAAR = "234123412346"
VALID_PAN = "ABCDE1234F"
MALFORMED_PAN = "ABCD1234F"  # only four leading letters
VALID_GSTIN = "27ABCDE1234F1Z5"
VALID_IFSC = "HDFC0001234"
VALID_UPI = "priya.sharma@okhdfcbank"
VALID_MOBILE = "+91 9876543210"


def kinds(matches) -> list[str]:
    return [match.kind for match in matches]


# --- Verhoeff ---------------------------------------------------------------


def test_verhoeff_accepts_known_good_values():
    for value in KNOWN_VALID:
        assert verhoeff_valid(value), value


def test_verhoeff_rejects_known_bad_values():
    for value in KNOWN_INVALID:
        assert not verhoeff_valid(value), value


def test_verhoeff_empty_and_nondigit_inputs_are_invalid():
    assert verhoeff_valid("") is False
    assert verhoeff_valid("no-digits-here") is False


def test_verhoeff_check_digit_round_trips():
    for payload in ("23412341234", "99994105705", "236"):
        check = verhoeff_check_digit(payload)
        assert verhoeff_valid(f"{payload}{check}")
        assert not verhoeff_valid(f"{payload}{(check + 1) % 10}")


def test_is_aadhaar_requires_twelve_digits_and_checksum():
    assert is_aadhaar(VALID_AADHAAR)
    assert is_aadhaar("2341 2341 2346")
    assert is_aadhaar("२३४१२३४१२३४६")
    assert not is_aadhaar("999941057059")
    assert not is_aadhaar("12345678901")  # 11 digits


# --- Aadhaar ----------------------------------------------------------------


def test_aadhaar_matches_contiguous_and_grouped_forms():
    assert [m.text for m in recognize_aadhaar(VALID_AADHAAR)] == [VALID_AADHAAR]
    assert [m.text for m in recognize_aadhaar("2341 2341 2346")] == ["2341 2341 2346"]
    assert [m.text for m in recognize_aadhaar("2341-2341-2346")] == ["2341-2341-2346"]


def test_aadhaar_rejects_verhoeff_failure():
    # Aadhaar-shaped but the checksum fails: a near-miss, not a match.
    assert recognize_aadhaar("999941057059") == []


def test_aadhaar_inside_a_longer_digit_run_is_not_a_match():
    embedded = f"9{VALID_AADHAAR}9"
    assert len(embedded) == 14
    assert recognize_aadhaar(embedded) == []
    assert find_all(embedded) == []


# --- PAN --------------------------------------------------------------------


def test_pan_matches_standalone():
    assert [m.text for m in recognize_pan(f"PAN: {VALID_PAN}.")] == [VALID_PAN]


def test_pan_rejects_malformed():
    assert recognize_pan(MALFORMED_PAN) == []
    assert recognize_pan("ABCDE12345") == []  # final char must be a letter


def test_pan_matches_lowercase_and_reports_original_span():
    # Case-insensitivity is a leak fix: a lowercase PAN must not egress
    # unredacted, and the reported span keeps the characters the user typed.
    text = "pan abcde1234f on file"
    matches = recognize_pan(text)
    assert [m.text for m in matches] == ["abcde1234f"]
    assert matches[0].start == 4
    assert text[matches[0].start : matches[0].end] == "abcde1234f"


# --- GSTIN ------------------------------------------------------------------


def test_gstin_matches_fifteen_characters():
    assert [m.text for m in recognize_gstin(f"GSTIN {VALID_GSTIN}.")] == [VALID_GSTIN]


def test_gstin_rejects_short():
    assert recognize_gstin("27ABCDE1234F1Z") == []


def test_gstin_matches_lowercase_and_reports_original_span():
    text = "gstin 27abcde1234f1z5 on file"
    matches = recognize_gstin(text)
    assert [m.text for m in matches] == ["27abcde1234f1z5"]
    assert text[matches[0].start : matches[0].end] == "27abcde1234f1z5"


def test_gstin_contains_pan_and_overlap_rule_reports_gstin_only():
    text = f"GSTIN {VALID_GSTIN} on file"
    # The PAN recognizer alone does fire inside the GSTIN...
    assert [m.text for m in recognize_pan(text)] == [VALID_PAN]
    # ...but find_all keeps only the enclosing GSTIN.
    matches = find_all(text)
    assert [m.kind for m in matches] == [KIND_GSTIN]
    assert matches[0].text == VALID_GSTIN


# --- IFSC -------------------------------------------------------------------


def test_ifsc_matches_and_rejects_bad_fifth_character():
    assert [m.text for m in recognize_ifsc(f"IFSC {VALID_IFSC}.")] == [VALID_IFSC]
    assert recognize_ifsc("HDFC1001234") == []  # 5th char must be 0


def test_ifsc_matches_lowercase_and_reports_original_span():
    text = "ifsc hdfc0001234 branch"
    matches = recognize_ifsc(text)
    assert [m.text for m in matches] == ["hdfc0001234"]
    assert text[matches[0].start : matches[0].end] == "hdfc0001234"


# --- UPI --------------------------------------------------------------------


def test_upi_matches_local_at_handle():
    assert [m.text for m in recognize_upi(f"pay to {VALID_UPI} today")] == [VALID_UPI]


def test_upi_does_not_match_a_dotted_email_domain():
    assert recognize_upi("reach me at priya@example.com") == []


def test_upi_overlaps_its_embedded_mobile_and_wins():
    text = "pay 9876543210@paytm now"
    assert [m.kind for m in find_all(text)] == [KIND_UPI]


# --- Mobile -----------------------------------------------------------------


def test_mobile_matches_prefixed_and_bare_forms():
    assert [m.text for m in recognize_mobile("call +91 9876543210")] == ["+91 9876543210"]
    assert [m.text for m in recognize_mobile("call +919876543210")] == ["+919876543210"]
    assert [m.text for m in recognize_mobile("call 9876543210")] == ["9876543210"]


def test_mobile_rejects_ten_digits_starting_zero_to_five():
    for prefix in "012345":
        assert recognize_mobile(f"{prefix}987654321") == []


def test_mobile_inside_a_longer_digit_run_is_not_a_match():
    assert recognize_mobile("98765432101") == []


# --- Devanagari digits ------------------------------------------------------


def test_devanagari_digit_run_matches_original_span():
    text = "संदर्भ १२३४५ खाते"
    matches = recognize_devanagari_digits(text)
    assert len(matches) == 1
    assert matches[0].text == "१२३४५"
    assert matches[0].kind == KIND_DEVANAGARI_DIGITS
    assert text[matches[0].start : matches[0].end] == "१२३४५"


def test_devanagari_written_aadhaar_reports_original_span():
    devanagari = to_devanagari(VALID_AADHAAR)
    text = f"आधार {devanagari} है"
    matches = recognize_aadhaar(text)
    assert len(matches) == 1
    assert matches[0].kind == KIND_AADHAAR
    assert matches[0].text == devanagari  # original Devanagari chars, not ASCII
    assert text[matches[0].start : matches[0].end] == devanagari


def test_devanagari_written_mobile_is_recognised_as_mobile():
    devanagari = to_devanagari("9876543210")
    assert [m.kind for m in find_all(f"फ़ोन {devanagari}")] == [KIND_MOBILE]


def test_devanagari_aadhaar_beats_generic_devanagari_run():
    devanagari = to_devanagari(VALID_AADHAAR)
    assert [m.kind for m in find_all(devanagari)] == [KIND_AADHAAR]


# --- find_all ---------------------------------------------------------------


def test_find_all_is_deterministic():
    text = (
        "Aadhaar 2341 2341 2346, PAN ABCDE1234F, mobile +91 9876543210, "
        "UPI priya.sharma@okhdfcbank, IFSC HDFC0001234."
    )
    first = find_all(text)
    second = find_all(text)
    assert first == second
    assert [(m.start, m.end, m.kind) for m in first] == [
        (m.start, m.end, m.kind) for m in second
    ]


def test_find_all_returns_sorted_non_overlapping_matches():
    text = (
        "GSTIN 27ABCDE1234F1Z5 and PAN ZYXWV9876U and "
        "mobile 9876543210 and code 1234 5678 9012"
    )
    matches = find_all(text)
    starts = [m.start for m in matches]
    assert starts == sorted(starts)
    for earlier, later in zip(matches, matches[1:]):
        assert earlier.end <= later.start
    assert KIND_PAN in kinds(matches)
    assert KIND_MOBILE in kinds(matches)


def test_find_all_reports_nothing_for_clean_text():
    assert find_all("The scheme covers eligible farmer families.") == []


def test_case_insensitive_matching_does_not_fire_on_high_entropy():
    # Widening to lowercase must not manufacture a match: an alternating
    # letter/digit token never contains the five consecutive letters that a
    # PAN, GSTIN, or IFSC needs, in either case.
    for token in ("A1B2C3D4E5F6G", "a1b2c3d4e5f6g"):
        assert find_all(f"Session token {token} was generated.") == []


def test_lowercase_gstin_overlap_still_reports_gstin_then_standalone_pan():
    text = "gstin 27abcde1234f1z5 and pan zyxwv9876u"
    matches = find_all(text)
    assert [m.kind for m in matches] == [KIND_GSTIN, KIND_PAN]
    assert matches[0].text == "27abcde1234f1z5"
    assert matches[1].text == "zyxwv9876u"


def test_recognizers_import_without_database_or_network():
    code = (
        "import socket\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network client constructed on import')\n"
        "socket.socket = _blocked\n"
        "import app.guardrails.recognizers as r\n"
        "import sys\n"
        "assert 'app.db' not in sys.modules\n"
        "assert 'app.rag' not in sys.modules\n"
        "assert r.verhoeff_valid('2363')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
