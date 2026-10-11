"""Effective-dated claim extraction, as-of resolution and anti-fabrication guards.

The suite pins the acceptance oracle (the FADCS rate ladder), the inclusive
boundary rule, the negative cases that must not fabricate a ladder, and -- most
importantly -- the R4 guarantee that every frozen claim's verbatim span really
appears in its named source file and that the fixture matches a fresh
extraction.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.temporal import (
    DatedClaim,
    TemporalLadderError,
    claim_from_dict,
    extract_claims,
    parse_effective_dates,
    resolve_as_of,
    supersession_chain,
)
from scripts.extract_temporal_claims import (
    DEFAULT_OUTPUT,
    GENERATOR,
    build_claims,
    load_fixture,
)

ROOT = Path(__file__).resolve().parent.parent

FADCS = ROOT / "data" / "myscheme" / "fadcs.md"
HDPS = ROOT / "data" / "myscheme" / "hdps.md"
LSSAS = ROOT / "data" / "myscheme" / "lssas.md"
AES = ROOT / "data" / "myscheme" / "aes.md"
DOT_PLI = ROOT / "data" / "myscheme" / "dot-pli-scheme.md"
ATD = ROOT / "data" / "myscheme" / "atd.md"
HSJPS = ROOT / "data" / "myscheme" / "hsjps.md"

# The acceptance oracle, verbatim from fadcs.md.
FADCS_LADDER = [
    (200, "2009-03-01"),
    (500, "2014-01-01"),
    (700, "2016-11-01"),
    (900, "2017-11-01"),
    (1100, "2018-11-01"),
    (1350, "2020-01-01"),
    (1600, "2021-04-01"),
    (1850, "2023-04-01"),
]

REQUIRED_CLAIM_KEYS = (
    "claim_id",
    "value",
    "unit",
    "effective_from",
    "superseded_by",
    "source",
    "span",
    "date_confidence",
)


def _claims(path: Path) -> list[DatedClaim]:
    return extract_claims(
        path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix()
    )


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_fadcs_reproduces_all_eight_oracle_values_with_dates():
    claims = _claims(FADCS)
    assert [(claim.value, claim.effective_from.isoformat()) for claim in claims] == (
        FADCS_LADDER
    )


def test_fadcs_last_claim_is_not_superseded():
    claims = _claims(FADCS)
    assert claims[-1].superseded_by is None
    for earlier, later in zip(claims, claims[1:]):
        assert earlier.superseded_by == later.claim_id


def test_fadcs_month_precision_only_for_the_january_2014_rung():
    claims = _claims(FADCS)
    confidences = {claim.value: claim.date_confidence for claim in claims}
    assert confidences[500] == "month"
    assert {value: confidence for value, confidence in confidences.items() if value != 500} == {
        value: "day" for value, _ in FADCS_LADDER if value != 500
    }


def test_resolution_is_inclusive_on_the_effective_date():
    claims = _claims(FADCS)
    assert resolve_as_of(claims, date(2021, 4, 1)).value == 1600
    assert resolve_as_of(claims, date(2021, 3, 31)).value == 1350
    assert resolve_as_of(claims, date(2021, 4, 2)).value == 1600


def test_resolution_handles_month_precision_and_iso_strings():
    claims = _claims(FADCS)
    assert resolve_as_of(claims, "2013-12-31").value == 200
    assert resolve_as_of(claims, "2014-01-01").value == 500
    assert resolve_as_of(claims, date(2000, 1, 1)) is None


def test_full_supersession_chain_from_the_first_claim():
    claims = _claims(FADCS)
    chain = supersession_chain(claims, claims[0].claim_id)
    assert [claim.value for claim in chain] == [value for value, _ in FADCS_LADDER]
    assert chain[-1].superseded_by is None


def test_walk_from_an_early_claim_reaches_the_tail():
    claims = _claims(FADCS)
    by_value = {claim.value: claim for claim in claims}
    chain = supersession_chain(claims, by_value[700].claim_id)
    assert [claim.value for claim in chain] == [700, 900, 1100, 1350, 1600, 1850]


def test_atd_two_formats_one_date_is_a_single_claim():
    claims = _claims(ATD)
    assert len(claims) == 1
    assert claims[0].value == 2500
    assert claims[0].effective_from == date(2021, 4, 1)
    assert claims[0].superseded_by is None
    assert len(supersession_chain(claims, claims[0].claim_id)) == 1


def test_hsjps_two_formats_one_date_is_a_single_claim():
    claims = _claims(HSJPS)
    assert len(claims) == 1
    assert claims[0].value == 10000
    assert claims[0].effective_from == date(2017, 11, 1)
    assert claims[0].superseded_by is None


def test_document_with_no_dates_yields_no_claims():
    assert extract_claims(
        "This scheme pays a monthly allowance of Rs. 500 to every family.",
        "data/myscheme/example.md",
    ) == []


def test_date_in_prose_with_no_value_yields_no_claim_but_is_parsed():
    text = "The scheme is effective from 1st April, 2019."
    assert extract_claims(text, "data/myscheme/example.md") == []
    assert parse_effective_dates(text) == [date(2019, 4, 1)]


def test_dot_pli_dates_are_prose_without_values():
    text = DOT_PLI.read_text(encoding="utf-8")
    assert parse_effective_dates(text) == [date(2021, 4, 1), date(2022, 4, 1)]
    assert extract_claims(text, DOT_PLI.relative_to(ROOT).as_posix()) == []


def test_reversed_range_raises_rather_than_reorders():
    text = "The rate is ₹500/- w.e.f. 01.04.2022 and ₹600/- w.e.f. 01.04.2021."
    with pytest.raises(TemporalLadderError, match="strictly increasing"):
        extract_claims(text, "data/myscheme/example.md")


def test_same_date_different_values_is_ambiguous():
    text = "The rate is ₹500/- w.e.f. 01.04.2021 and ₹600/- w.e.f. 01.04.2021."
    with pytest.raises(TemporalLadderError, match="strictly increasing"):
        extract_claims(text, "data/myscheme/example.md")


def test_unknown_claim_id_in_chain_raises():
    claims = _claims(FADCS)
    with pytest.raises(KeyError):
        supersession_chain(claims, "does-not-exist")


def test_fixture_matches_a_fresh_extraction():
    header, records = load_fixture()
    fresh_header, fresh_records = build_claims()
    assert header["generator"] == GENERATOR
    assert header["type"] == "header"
    assert header["claims"] == len(records)
    assert header["ladder_problems"] == []
    assert records == fresh_records
    assert header["claims"] == fresh_header["claims"]


def test_fixture_supersession_links_resolve_within_each_source():
    _, records = load_fixture()
    claims = [claim_from_dict(record) for record in records]
    by_id = {claim.claim_id: claim for claim in claims}
    for claim in claims:
        if claim.superseded_by is not None:
            successor = by_id[claim.superseded_by]
            assert successor.source == claim.source
            assert successor.effective_from > claim.effective_from
            assert successor.value != claim.value
    for source in {claim.source for claim in claims}:
        tail = [claim for claim in claims if claim.source == source and claim.superseded_by is None]
        assert len(tail) == 1, f"{source} must have exactly one un-superseded claim"


def test_every_record_carries_the_required_claim_fields():
    _, records = load_fixture()
    for record in records:
        for key in REQUIRED_CLAIM_KEYS:
            assert key in record, f"fixture record missing {key!r}: {record}"
        assert record["date_confidence"] in {"day", "month"}


def test_every_frozen_span_literally_appears_in_its_named_source():
    _, records = load_fixture()
    assert records
    for record in records:
        source = ROOT / record["source"]
        assert source.is_file(), f"missing source file {record['source']}"
        source_text = _normalise(source.read_text(encoding="utf-8"))
        span = _normalise(record["span"])
        assert span in source_text, (
            f"fabricated claim: span does not appear in {record['source']}: "
            f"{span!r}"
        )


def test_check_mode_reports_the_fixture_current():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/extract_temporal_claims.py",
            "--check",
            "--output",
            str(DEFAULT_OUTPUT),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "fixture is current" in result.stdout


def test_fixture_file_is_lf_and_header_first():
    raw = DEFAULT_OUTPUT.read_bytes()
    assert b"\r\n" not in raw
    first = json.loads(raw.decode("utf-8").splitlines()[0])
    assert first["type"] == "header"


def test_temporal_module_imports_no_database_or_rag():
    code = (
        "import socket\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network client constructed on import')\n"
        "socket.socket = _blocked\n"
        "import app.temporal\n"
        "import sys\n"
        "assert 'app.db' not in sys.modules\n"
        "assert 'app.rag' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
