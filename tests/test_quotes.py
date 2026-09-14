"""Quote parsing + verification (pure functions, no DB/LLM)."""

from app.quotes import ParsedQuote, parse_quotes, verify_quotes

SOURCE_A = {
    "source": "schemes/pm-kisan.md",
    "data_status": "sample_verified",
    "content": (
        "PM-KISAN provides income support of Rs 6,000 per year to eligible "
        "landholding farmer families in India, paid directly into their bank "
        "accounts through Direct Benefit Transfer (DBT)."
    ),
}
SOURCE_B = {
    "source": "schemes/pm-sym.md",
    "data_status": "sample_verified",
    "content": "PM-SYM offers a monthly pension to unorganised workers.",
}


def test_parse_extracts_well_formed_quotes():
    text = (
        "Here is the answer.\n"
        "> PM-KISAN provides income support of Rs 6,000 per year to eligible landholding "
        "farmer families in India, paid directly into their bank accounts through Direct "
        "Benefit Transfer (DBT). [schemes/pm-kisan.md, sample_verified]\n"
        "And a second line without a bracket is ignored.\n"
        "> only a source, no status [schemes/pm-sym.md]\n"
    )
    quotes = parse_quotes(text)
    assert len(quotes) == 2
    assert quotes[0].text.startswith("PM-KISAN provides income support")
    assert quotes[0].source == "schemes/pm-kisan.md"
    assert quotes[0].status == "sample_verified"
    assert quotes[1].source == "schemes/pm-sym.md"
    assert quotes[1].status is None


def test_parse_ignores_plain_lines():
    assert parse_quotes("no quotes here\n> still not a quote without bracket") == []


def test_verify_accepts_verbatim_quote_from_matching_source():
    parsed = [
        ParsedQuote(
            text=(
                "PM-KISAN provides income support of Rs 6,000 per year to eligible "
                "landholding farmer families in India, paid directly into their bank "
                "accounts through Direct Benefit Transfer (DBT)."
            ),
            source="schemes/pm-kisan.md",
            status="sample_verified",
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A, SOURCE_B])
    assert out[0].verified is True
    assert out[0].matched_source == "schemes/pm-kisan.md"


def test_verify_accepts_punctuation_different_quote():
    # Same words, different punctuation/case should still verify.
    parsed = [
        ParsedQuote(
            text="Pm Kisan provides income support, of Rs 6,000 per year, to eligible "
            "landholding farmer families in India",
            source="schemes/pm-kisan.md",
            status="sample_verified",
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A])
    assert out[0].verified is True


def test_verify_rejects_quote_without_required_data_status():
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="schemes/pm-sym.md",
            status=None,
        )
    ]

    out = verify_quotes(parsed, [SOURCE_B])

    assert out[0].verified is False
    assert out[0].matched_source is None


def test_verify_rejects_fuzzy_paraphrase_that_is_not_an_exact_normalized_substring():
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension for unorganised workers.",
            source="schemes/pm-sym.md",
            status="sample_verified",
        )
    ]

    out = verify_quotes(parsed, [SOURCE_B])

    assert out[0].verified is False


def test_verify_rejects_fabricated_quote():
    parsed = [
        ParsedQuote(
            text="The government grants each citizen a free unicorn every year.",
            source="schemes/pm-kisan.md",
            status="sample_verified",
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A, SOURCE_B])
    assert out[0].verified is False
    assert out[0].matched_source is None


def test_verify_rejects_quote_when_named_source_was_not_retrieved():
    """Text from another document must not validate a fabricated citation."""
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="schemes/not-retrieved.md",
            status=None,
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A, SOURCE_B])
    assert out[0].verified is False
    assert out[0].matched_source is None


def test_verify_rejects_same_basename_from_a_different_source_path():
    """Basename collisions must not let the wrong jurisdiction verify a quote."""
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="states/pm-sym.md",
            status=None,
        )
    ]
    out = verify_quotes(parsed, [SOURCE_B])
    assert out[0].verified is False
    assert out[0].matched_source is None


def test_verify_rejects_declared_status_when_source_status_is_unknown():
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="schemes/pm-sym.md",
            status="sample_verified",
        )
    ]
    source = {key: value for key, value in SOURCE_B.items() if key != "data_status"}
    out = verify_quotes(parsed, [source])
    assert out[0].verified is False


def test_verify_rejects_mismatched_data_status():
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="schemes/pm-sym.md",
            status="sample_verified",
        )
    ]
    source = {**SOURCE_B, "data_status": "directory_seed"}
    out = verify_quotes(parsed, [source])
    assert out[0].verified is False
    assert out[0].matched_source is None
