#!/usr/bin/env python3
"""Dependency-free validator for the SchemeGPT data corpus.

Run from the project root (or anywhere — all paths are resolved relative to
this script's location):

    python scripts/validate_data.py

Exit code 0 with a compact summary when every check passes; a non-zero exit
code with explained errors otherwise. Uses only the Python standard library
so it works without installing the project's dependencies.

Checks:
  - exactly 36 unique states/UTs (28 states + 8 union territories)
  - every state/UT Markdown file and scheme-catalog entry exists
  - every catalog ``source_file`` exists on disk
  - ``data_status`` is one of the allowed values
  - official/source URLs are https
  - no duplicate catalog ids or source files
  - every ``*.json`` file under ``data/`` and ``eval/`` parses
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

STATES_CATALOG_FILE = ROOT_DIR / "data" / "india_states.json"
SCHEME_CATALOG_FILE = ROOT_DIR / "data" / "scheme_catalog.json"
STATES_MD_DIR = ROOT_DIR / "data" / "states"
SCHEMES_MD_DIR = ROOT_DIR / "data" / "schemes"

# data_status values used consistently across the corpus. The existing six
# central sample docs are ``sample_verified``; every state/UT record is
# ``directory_seed``. Do not add a value here without updating the data docs.
ALLOWED_DATA_STATUS = {"sample_verified", "directory_seed"}

EXPECTED_STATE_COUNT = 36
EXPECTED_STATE_SUBTYPE_COUNT = 28
EXPECTED_UT_COUNT = 8

# URL fields that must be https when present.
_HTTPS_URL_FIELDS = ("source_url", "discovery_url")

_errors: list[str] = []


def _error(message: str) -> None:
    _errors.append(message)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(path)


def _slugify(name: str) -> str:
    """Same slug rule as ``app.catalog.slugify`` (re-implemented here so the
    validator stays dependency-free)."""
    text = str(name).lower().replace("(", " ").replace(")", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _load_json(path: Path, label: str):
    if not path.is_file():
        _error(f"{label}: file not found: {_rel(path)}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _error(f"{label}: invalid JSON in {_rel(path)}: {exc}")
        return None


def _record_list(data, path: Path) -> list[dict]:
    if not isinstance(data, dict):
        _error(f"{_rel(path)} must contain a JSON object with a 'records' list")
        return []
    records = data.get("records")
    if not isinstance(records, list):
        _error(f"{_rel(path)} must contain a JSON 'records' list")
        return []
    return [record for record in records if isinstance(record, dict)]


def _check_states_catalog() -> list[dict]:
    """Load india_states.json and enforce the 36-jurisdiction contract."""
    data = _load_json(STATES_CATALOG_FILE, "states catalog")
    records = _record_list(data, STATES_CATALOG_FILE) if data is not None else []

    if len(records) != EXPECTED_STATE_COUNT:
        _error(
            f"states catalog: expected exactly {EXPECTED_STATE_COUNT} "
            f"jurisdictions, found {len(records)}"
        )

    state_count = sum(
        1 for r in records if r.get("type") == "state"
    )
    ut_count = sum(
        1 for r in records if r.get("type") == "union_territory"
    )
    if state_count != EXPECTED_STATE_SUBTYPE_COUNT:
        _error(
            f"states catalog: expected {EXPECTED_STATE_SUBTYPE_COUNT} states, "
            f"found {state_count}"
        )
    if ut_count != EXPECTED_UT_COUNT:
        _error(f"states catalog: expected {EXPECTED_UT_COUNT} UTs, found {ut_count}")

    names: set[str] = set()
    codes: set[str] = set()
    for record in records:
        name = str(record.get("name") or "").strip()
        code = str(record.get("code") or "").strip()
        if not name:
            _error("states catalog: a record has no 'name'")
        elif name in names:
            _error(f"states catalog: duplicate name: {name}")
        names.add(name)
        if not code:
            _error("states catalog: a record has no 'code'")
        elif code in codes:
            _error(f"states catalog: duplicate code: {code}")
        codes.add(code)

        status = str(record.get("data_status") or "")
        if status not in ALLOWED_DATA_STATUS:
            _error(
                f"states catalog {name or code or '(unnamed)'}: invalid "
                f"data_status {status!r} (allowed: "
                f"{', '.join(sorted(ALLOWED_DATA_STATUS))})"
            )

        for field in _HTTPS_URL_FIELDS:
            value = str(record.get(field) or "")
            if value and not value.startswith("https://"):
                _error(
                    f"states catalog {name or code}: {field} must be https: "
                    f"{value!r}"
                )

    return records


def _check_state_files_and_catalog(records: list[dict]) -> set[str]:
    """Every state/UT must have a Markdown file and a scheme-catalog entry."""
    scheme_data = _load_json(SCHEME_CATALOG_FILE, "scheme catalog")
    scheme_records = (
        _record_list(scheme_data, SCHEME_CATALOG_FILE)
        if scheme_data is not None
        else []
    )
    by_code = {
        str(record.get("code") or "").lower(): record
        for record in scheme_records
        if str(record.get("code") or "").lower()
    }
    found_codes: set[str] = set()

    for record in records:
        name = str(record.get("name") or "")
        code = str(record.get("code") or "")
        slug = _slugify(name)
        md_file = STATES_MD_DIR / f"{slug}.md"
        if not md_file.is_file():
            _error(
                f"state entry {name} ({code}): missing Markdown file: "
                f"data/states/{slug}.md"
            )
        if not code:
            continue  # name/code errors already reported above
        catalog_entry = by_code.get(code.lower())
        if catalog_entry is None:
            _error(
                f"state entry {name} ({code}): no matching entry in "
                f"data/scheme_catalog.json (looked up by code {code})"
            )
        else:
            found_codes.add(code.lower())

    return found_codes


def _check_scheme_catalog() -> None:
    """Catalog-wide checks: source_file exists, data_status allowed, https
    URLs, and no duplicate ids or source files."""
    data = _load_json(SCHEME_CATALOG_FILE, "scheme catalog")
    records = _record_list(data, SCHEME_CATALOG_FILE) if data is not None else []

    ids: set[str] = set()
    source_files: set[str] = set()
    for record in records:
        record_id = str(record.get("id") or "")
        if not record_id:
            _error("scheme catalog: a record has no 'id'")
        elif record_id in ids:
            _error(f"scheme catalog: duplicate id: {record_id}")
        ids.add(record_id)

        status = str(record.get("data_status") or "")
        if status not in ALLOWED_DATA_STATUS:
            _error(
                f"scheme catalog {record_id or '(no id)'}: invalid data_status "
                f"{status!r} (allowed: {', '.join(sorted(ALLOWED_DATA_STATUS))})"
            )

        source_file = str(record.get("source_file") or "")
        if not source_file:
            _error(f"scheme catalog {record_id or '(no id)'}: missing source_file")
            continue
        source_path = (ROOT_DIR / source_file).resolve()
        if not source_path.is_file():
            _error(
                f"scheme catalog {record_id}: source_file does not exist: "
                f"{source_file}"
            )
        if source_file in source_files:
            _error(f"scheme catalog: duplicate source_file: {source_file}")
        source_files.add(source_file)

        # The six verified sample records must live under data/schemes/ and the
        # directory seeds under data/states/.
        if status == "sample_verified" and not source_file.startswith("data/schemes/"):
            _error(
                f"scheme catalog {record_id}: sample_verified source_file must "
                f"be under data/schemes/, got {source_file!r}"
            )
        if status == "directory_seed" and not source_file.startswith("data/states/"):
            _error(
                f"scheme catalog {record_id}: directory_seed source_file must "
                f"be under data/states/, got {source_file!r}"
            )

        for field in _HTTPS_URL_FIELDS:
            value = str(record.get(field) or "")
            if value and not value.startswith("https://"):
                _error(
                    f"scheme catalog {record_id}: {field} must be https: "
                    f"{value!r}"
                )


def _check_markdown_https_links() -> None:
    """No plain-http links in any ingested Markdown source."""
    pattern = re.compile(r"https?://")
    for directory in (SCHEMES_MD_DIR, STATES_MD_DIR):
        if not directory.is_dir():
            _error(f"Markdown directory not found: {_rel(directory)}")
            continue
        for md_file in sorted(directory.glob("*.md")):
            for line_no, line in enumerate(
                md_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                for match in pattern.finditer(line):
                    if not match.group(0).startswith("https://"):
                        _error(
                            f"{_rel(md_file)}:{line_no}: non-https link found: "
                            f"{line.strip()!r}"
                        )


def _check_all_json_parse() -> None:
    """Every JSON file in data/ and eval/ must parse (plus this run's two
    main data files which were already parsed)."""
    for directory in (ROOT_DIR / "data", ROOT_DIR / "eval"):
        if not directory.is_dir():
            continue
        for json_file in sorted(directory.glob("*.json")):
            try:
                json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                _error(f"invalid JSON in {_rel(json_file)}: {exc}")


def _summary(records: list[dict], state_codes: set[str]) -> str:
    catalog = _load_json(SCHEME_CATALOG_FILE, "scheme catalog")
    scheme_records = (
        _record_list(catalog, SCHEME_CATALOG_FILE) if catalog is not None else []
    )
    total = len(scheme_records)
    sample_count = sum(
        1 for r in scheme_records if r.get("data_status") == "sample_verified"
    )
    seed_count = sum(
        1 for r in scheme_records if r.get("data_status") == "directory_seed"
    )
    state_count = sum(
        1 for r in records if r.get("type") == "state"
    )
    ut_count = sum(
        1 for r in records if r.get("type") == "union_territory"
    )
    return (
        f"OK: {len(records)} jurisdictions ({state_count} states + {ut_count} UTs); "
        f"{total} catalog records ({sample_count} sample_verified + "
        f"{seed_count} directory_seed); {len(state_codes)} state/UT catalog "
        f"entries matched; all source files present; all JSON parses."
    )


def main() -> int:
    global _errors
    _errors = []

    states = _check_states_catalog()
    matched_codes = _check_state_files_and_catalog(states)
    _check_scheme_catalog()
    _check_markdown_https_links()
    _check_all_json_parse()

    if _errors:
        print("Data validation FAILED:", file=sys.stderr)
        for error in _errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            f"\n{len(_errors)} error(s). Fix the data files and re-run.",
            file=sys.stderr,
        )
        return 1

    print(_summary(states, matched_codes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
