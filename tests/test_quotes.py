"""Quote parsing + verification (pure functions, no DB/LLM)."""

from app.quotes import ParsedQuote, parse_quotes, verify_quotes

SOURCE_A = {
    "source": "schemes/pm-kisan.md",
    "content": (
        "PM-KISAN provides income support of Rs 6,000 per year to eligible "
        "landholding farmer families in India, paid directly into their bank "
        "accounts through Direct Benefit Transfer (DBT)."
    ),
}
SOURCE_B = {
    "source": "schemes/pm-sym.md",
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
            status=None,
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A])
    assert out[0].verified is True


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


def test_verify_falls_back_to_other_sources_when_named_source_absent():
    # Named source isn't in the retrieved set, but the text is in another source.
    parsed = [
        ParsedQuote(
            text="PM-SYM offers a monthly pension to unorganised workers.",
            source="schemes/not-retrieved.md",
            status=None,
        )
    ]
    out = verify_quotes(parsed, [SOURCE_A, SOURCE_B])
    assert out[0].verified is True
    assert out[0].matched_source == "schemes/pm-sym.md"
