"""Reversible PII vault tests: pure, offline, no database.

These pin the request-scoped lifecycle: one mapping per request, deterministic
within it, unreusable across requests, never exposed by ``repr``, and safe to
apply to text it did not produce.
"""

from __future__ import annotations

from app.guardrails.vault import Vault, restore, tokenize

AADHAAR = "234123412346"
PAN = "ABCDE1234F"
MOBILE = "+91 9876543210"
UPI = "priya.sharma@okhdfcbank"


def test_vault_round_trip_restores_the_original_exactly():
    text = (
        f"Aadhaar {AADHAAR}, PAN {PAN}, mobile {MOBILE}, "
        f"UPI {UPI} today."
    )
    vault = Vault()
    redacted, mapping = vault.tokenize(text)

    for identifier in (AADHAAR, PAN, "9876543210", UPI):
        assert identifier not in redacted
    assert mapping is vault
    assert mapping.restore(redacted) == text


def test_same_value_maps_to_same_placeholder_within_a_request():
    vault = Vault()
    redacted, _ = vault.tokenize(f"aadhaar {AADHAAR} and again {AADHAAR}")

    assert AADHAAR not in redacted
    tokens = [part for part in redacted.split() if part.startswith("[[PII:")]
    assert len(tokens) == 2
    assert tokens[0] == tokens[1]  # one placeholder reused for the repeat
    assert vault.restore(redacted) == f"aadhaar {AADHAAR} and again {AADHAAR}"


def test_two_requests_with_same_identifier_do_not_share_a_mapping():
    request_a = Vault()
    request_b = Vault()
    redacted_a, mapping_a = request_a.tokenize(f"my aadhaar {AADHAAR}")
    redacted_b, mapping_b = request_b.tokenize(f"my aadhaar {AADHAAR}")

    assert AADHAAR not in redacted_a and AADHAAR not in redacted_b
    # Per-request nonce: the same value tokenises to a different placeholder in
    # a different request, so one request's mapping cannot unmask the other's.
    assert redacted_a != redacted_b
    assert mapping_a.restore(redacted_b) == redacted_b
    assert mapping_b.restore(redacted_a) == redacted_a
    # Each mapping still works on its own request.
    assert mapping_a.restore(redacted_a) == f"my aadhaar {AADHAAR}"
    assert mapping_b.restore(redacted_b) == f"my aadhaar {AADHAAR}"


def test_no_pii_text_passes_through_byte_identical():
    text = "The scheme covers eligible farmer families."
    vault = Vault()
    redacted, mapping = vault.tokenize(text)

    assert redacted == text
    assert mapping is vault
    assert not vault.has_matches


def test_restore_without_placeholders_is_a_noop():
    vault = Vault()
    text = "No identifiers here at all, just policy text."
    assert vault.restore(text) == text
    assert Vault().restore("") == ""


def test_restore_does_not_corrupt_a_partial_placeholder():
    vault = Vault()
    redacted, _ = vault.tokenize(f"aadhaar {AADHAAR}")
    assert "]]" in redacted

    truncated = redacted[: redacted.index("]]")]
    assert vault.restore(truncated) == truncated
    assert vault.restore("[[PII:") == "[[PII:"
    assert vault.restore("[[PII:deadbeef:PAN:1]") == "[[PII:deadbeef:PAN:1]"


def test_lowercase_identifier_is_tokenised_and_restored_exactly():
    # Ties the vault to the case-insensitivity fix: a lowercase PAN is a leak if
    # it is not tokenised, and restoration must preserve the user's casing.
    vault = Vault()
    redacted, _ = vault.tokenize("pan mljmi4203y on file")
    assert "mljmi4203y" not in redacted
    assert vault.restore(redacted) == "pan mljmi4203y on file"


def test_mapping_is_not_exposed_by_repr_or_str():
    vault = Vault()
    vault.tokenize(f"aadhaar {AADHAAR}")
    assert AADHAAR not in repr(vault)
    assert AADHAAR not in str(vault)
    assert "PII" not in repr(vault)
    assert "mapping withheld" in repr(vault)


def test_context_manager_clears_the_mapping_on_exit():
    with Vault() as vault:
        redacted, _ = vault.tokenize(f"aadhaar {AADHAAR}")
        assert vault.has_matches
    assert not vault.has_matches
    assert vault.restore(redacted) == redacted  # nothing left to restore


def test_module_level_tokenize_and_restore_convenience():
    redacted, mapping = tokenize(f"aadhaar {AADHAAR}")
    assert AADHAAR not in redacted
    assert restore(redacted, mapping) == f"aadhaar {AADHAAR}"
