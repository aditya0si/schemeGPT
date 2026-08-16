"""Loaders for the nationwide states catalog and the scheme recommendation catalog.

Pure local-file loaders with no database, vector store, or network dependency,
so ingestion, recommendations, and the API can all use them without side
effects. All loaders are ``lru_cache``d; the data files are treated as the
source of truth and read once per process.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import ROOT_DIR

STATES_CATALOG_FILE = ROOT_DIR / "data" / "india_states.json"
SCHEME_CATALOG_FILE = ROOT_DIR / "data" / "scheme_catalog.json"


def slugify(name: str) -> str:
    """Lowercase hyphenated slug used for state/UT Markdown filenames."""
    text = str(name).lower().replace("(", " ").replace(")", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def normalize_name(name: str) -> str:
    """Punctuation-insensitive state/UT name normalization.

    The same rule used by ``app.recommend._normalize``: lowercase, then replace
    every run of non-alphanumeric characters (punctuation and whitespace) with
    a single space, and strip leading/trailing whitespace. This makes lookups
    agree on spellings such as ``"Delhi (NCT)"`` and ``"Delhi NCT"`` while the
    original names in responses are always preserved verbatim.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _records(data, filename: Path) -> list[dict]:
    if not isinstance(data, dict):
        return []
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{filename} must contain a JSON 'records' list")
    return [dict(record) for record in records]


@lru_cache
def load_states_catalog() -> list[dict]:
    """All 36 state/UT records from ``data/india_states.json`` in stable file order."""
    data = json.loads(STATES_CATALOG_FILE.read_text(encoding="utf-8"))
    return _records(data, STATES_CATALOG_FILE)


@lru_cache
def load_states_by_name() -> dict[str, dict]:
    """Case- and punctuation-insensitive lookup of a state/UT record by name or code.

    Keys are normalized with the same rule as ``app.recommend._normalize``, so
    a profile value such as ``"Delhi NCT"`` resolves the catalog's
    ``"Delhi (NCT)"`` record. The stored ``name`` (never the normalized key) is
    returned so responses preserve the exact catalog name.
    """
    lookup: dict[str, dict] = {}
    for record in load_states_catalog():
        name = str(record.get("name") or "")
        code = str(record.get("code") or "")
        normalized_name = normalize_name(name)
        if normalized_name:
            lookup[normalized_name] = record
        if code:
            lookup[normalize_name(code)] = record
    return lookup


@lru_cache
def load_scheme_catalog_records() -> list[dict]:
    """All records (central schemes + state/UT seeds) from ``data/scheme_catalog.json``."""
    data = json.loads(SCHEME_CATALOG_FILE.read_text(encoding="utf-8"))
    return _records(data, SCHEME_CATALOG_FILE)


# Honest framing of what the corpus actually is. Deliberately avoids the word
# "all schemes": the corpus is a nationwide discovery/coverage directory plus a
# small set of verified central sample records.
COVERAGE_NOTE = (
    "The corpus is a nationwide state/UT discovery directory, not an exhaustive "
    "verified scheme database. Every state/Union Territory record is a "
    "directory_seed: it maps the jurisdiction and links to the official national "
    "MyScheme discovery portal for further search. Only the central sample "
    "records are verified (data_status: sample_verified). Scheme-level "
    "eligibility for any state/UT has not been individually verified yet, and "
    "no claim is made that all government schemes have been ingested."
)


def coverage_summary() -> dict:
    """Transparency report over the local catalog files (pure, side-effect free).

    Derived entirely from ``data/india_states.json`` and
    ``data/scheme_catalog.json``. Reports the jurisdiction count (28 states + 8
    UTs), the catalog totals broken down by ``data_status``, and a per
    jurisdiction status/count line, plus a truthful ``coverage_note``.
    """
    states = load_states_catalog()
    records = load_scheme_catalog_records()

    state_records = [
        record for record in states if record.get("type") == "state"
    ]
    ut_records = [
        record for record in states if record.get("type") == "union_territory"
    ]

    catalog_by_status: dict[str, int] = {}
    for record in records:
        status = str(record.get("data_status") or "unknown")
        catalog_by_status[status] = catalog_by_status.get(status, 0) + 1

    # Per-jurisdiction lines: one scheme-catalog record per jurisdiction is
    # expected today (its directory seed); the count stays meaningful if a
    # jurisdiction ever gains verified scheme records.
    per_jurisdiction: list[dict] = []
    for record in states:
        name = record.get("name")
        per_jurisdiction.append(
            {
                "name": name,
                "code": record.get("code"),
                "type": record.get("type"),
                "data_status": record.get("data_status") or "directory_seed",
                "catalog_record_count": sum(
                    1
                    for entry in records
                    if entry.get("jurisdiction") == name
                ),
            }
        )

    return {
        "jurisdiction_count": len(states),
        "state_count": len(state_records),
        "union_territory_count": len(ut_records),
        "state_names": [record.get("name") for record in state_records],
        "union_territory_names": [record.get("name") for record in ut_records],
        "catalog_records_total": len(records),
        "catalog_sample_verified_count": catalog_by_status.get(
            "sample_verified", 0
        ),
        "catalog_directory_seed_count": catalog_by_status.get(
            "directory_seed", 0
        ),
        "catalog_by_status": catalog_by_status,
        "per_jurisdiction": per_jurisdiction,
        "coverage_note": COVERAGE_NOTE,
    }


@lru_cache
def load_schemes_by_source() -> dict[str, dict]:
    """Map a source filename to its catalog record.

    Keys are stored both project-relative (``data/schemes/pm-kisan.md``) and
    data-root-relative (``schemes/pm-kisan.md``) so ingestion can look up the
    metadata it needs no matter how the source path is expressed.
    """
    lookup: dict[str, dict] = {}
    for record in load_scheme_catalog_records():
        source = record.get("source_file") or ""
        if not source:
            continue
        lookup[source] = record
        if source.startswith("data/"):
            lookup[source[len("data/"):]] = record
    return lookup
