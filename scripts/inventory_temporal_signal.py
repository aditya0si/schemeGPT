"""Inventory the real temporal signal in the SchemeGPT corpus (stdlib-only).

This is the *honesty* instrument for the version-history track. The corpus is a
single snapshot; before any "answer as of a date" feature is built we need to
know how many documents actually declare when they took effect, and how many
carry only a non-authoritative date (a fetch/verification date or a filename
year), and how many carry no temporal signal at all.

It reads the three ingested Markdown trees -- ``data/myscheme``,
``data/schemes`` and ``data/states`` -- plus ``data/scheme_catalog.json`` and
the cached PDF directory ``data/.cache/myscheme_pdfs``. It makes no network
call, imports nothing outside the standard library, and can write nothing: it
only reads and prints.

Classification (exactly one class per document):

``declared``
    The document contains a *declared effective / amendment / notification*
    clause: ``w.e.f.``, ``with effect from``, ``effective from``,
    ``came into force``, ``came into effect``, ``as amended by``,
    ``amended by``, ``amended vide``, ``inserted by``, ``substituted by``,
    a notification/order/gazette reference followed by ``dated``, a bare
    ``dated <date>``, or ``revised ... <date>`` -- and a *specific* calendar
    date occurs within a short window of the clause. A declared date is usable
    as fact. ``as on <date>`` is searched and reported but excluded from this
    class: in this corpus it is always an eligibility reference date, not an
    effective date (see ``NON_QUALIFYING_PATTERNS``).

``inferred``
    No declared clause, but the document's *record* carries a non-authoritative
    date: the front-matter ``Checked on`` / ``Last verified`` line (the 42
    catalog records), the ``last_verified`` field in ``data/scheme_catalog.json``,
    or a four-digit year embedded in the *filename* (e.g. ``kmys2016.md``).
    These are hints about when the text was captured, never when it took effect.

``none``
    No declared clause and no recorded non-authoritative date.

File mtimes exist for every file and are reported as a range, but they are
deliberately **not** used to promote a document to ``inferred``: cloning and
copying rewrite mtimes, so a universal mtime carries no per-document
information about when the document took effect. Pass ``--count-mtime`` to see
the (useless, degenerate) counts that result if mtimes are counted as a signal.

Usage:
    ./.venv/Scripts/python.exe scripts/inventory_temporal_signal.py
    ./.venv/Scripts/python.exe scripts/inventory_temporal_signal.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CORPUS_DIRS = ("data/myscheme", "data/schemes", "data/states")
CATALOG = Path("data/scheme_catalog.json")
PDF_CACHE = Path("data/.cache/myscheme_pdfs")
CENTRAL_SCHEMES = (
    "data/schemes/pm-kisan.md",
    "data/schemes/ayushman-bharat.md",
    "data/schemes/pmay-g.md",
    "data/schemes/pm-sym.md",
    "data/schemes/gst.md",
    "data/schemes/startup-india.md",
)

# A *specific* calendar date: day+month+year, or month+year. A bare year does
# NOT qualify: "the revised tractor scheme ... by 2022" is a target year, not an
# effective date, and counting it would manufacture temporal signal.
DATE_RE = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"  # 01.04.2021, 1-1-2014, 20/08/2015
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December),?\s+\d{4}\b"  # 1st April 2017
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4}\b"  # April 1, 2017
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December),?\s+\d{4}\b",  # February 2019
    re.IGNORECASE,
)

# Effective / amendment / notification clauses. A match only counts when a
# *specific* calendar date (see DATE_RE) occurs within ``WINDOW`` characters.
# Keys are the human-facing pattern names reported in the doc; values are the
# compiled regexes.
#
# ``as on <date>`` is searched and reported (it is in the brief's pattern list)
# but is deliberately NOT counted toward ``declared``: inspection shows that in
# this corpus it always marks an eligibility reference date ("age as on
# 25.05.2022", "sales as on 30.11.2023"), never the document's own effective or
# amendment date. Counting it would inflate the temporal signal.
NON_QUALIFYING_PATTERNS = {"as on <date>"}

DECLARED_PATTERNS: dict[str, re.Pattern[str]] = {
    "w.e.f": re.compile(r"\bw\s*\.\s*e\s*\.\s*f\.?\b", re.IGNORECASE),
    "with effect from": re.compile(r"\bwith effect from\b", re.IGNORECASE),
    "effective from": re.compile(r"\beffective from\b", re.IGNORECASE),
    "came into force": re.compile(r"\bcame into force\b", re.IGNORECASE),
    "came into effect": re.compile(r"\bcame into effect\b", re.IGNORECASE),
    "as amended by": re.compile(r"\bas amended by\b", re.IGNORECASE),
    "amended by": re.compile(r"\bamended by\b", re.IGNORECASE),
    "amended vide": re.compile(r"\bamended vide\b", re.IGNORECASE),
    "inserted by": re.compile(r"\binserted by\b", re.IGNORECASE),
    "substituted by": re.compile(r"\bsubstituted by\b", re.IGNORECASE),
    "amendment ... dated": re.compile(
        r"\bamend(?:ment|ed)\b[^.\n]{0,60}\bdated\b", re.IGNORECASE
    ),
    "notification/order ... dated": re.compile(
        r"\b(?:notification|order|circular|memorandum|resolution|gazette|"
        r"letter|g\.?r\.?|o\.?m\.?)\b[^.\n]{0,80}\bdated\b",
        re.IGNORECASE,
    ),
    "dated <date>": re.compile(r"\bdated\b", re.IGNORECASE),
    "as on <date>": re.compile(r"\bas on\b", re.IGNORECASE),
    "revised ... <date>": re.compile(r"\brevis(?:ed|ing)\b", re.IGNORECASE),
}

# Non-authoritative date signals that live in the document text and mark a
# record's own capture/verification date rather than an effective date.
CONTENT_HINT_RE = re.compile(
    r"\*\*(?:Checked on|Last verified|Verified on)\*\*[^\n]*\d{4}",
    re.IGNORECASE,
)
FILENAME_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

WINDOW = 100  # characters either side of a clause in which a date must sit

# A rate/value that moved: the clause "w.e.f"/"with effect from" appears with a
# distinct date at least this many times in one document.
MIN_EFFECT_DATES = 2


@dataclass
class DocResult:
    rel_path: str
    klass: str
    declared_matches: dict[str, list[str]] = field(default_factory=dict)
    content_hint: bool = False
    filename_year: str | None = None
    mtime: str = ""
    effect_dates: list[str] = field(default_factory=list)


def classify(text: str, rel_path: str) -> DocResult:
    rel = rel_path.replace("\\", "/")
    result = DocResult(rel_path=rel, klass="none")

    for name, pattern in DECLARED_PATTERNS.items():
        hits: list[str] = []
        for match in pattern.finditer(text):
            lo = max(0, match.start() - WINDOW)
            hi = min(len(text), match.end() + WINDOW)
            if DATE_RE.search(text[lo:hi]):
                snippet = " ".join(text[match.start() : match.end() + 60].split())
                hits.append(snippet[:140])
        if hits:
            result.declared_matches[name] = hits

    stem = Path(rel_path).stem
    year_match = FILENAME_YEAR_RE.search(stem)
    if year_match:
        result.filename_year = year_match.group(0)

    result.content_hint = bool(CONTENT_HINT_RE.search(text))

    qualifying = [
        name
        for name in result.declared_matches
        if name not in NON_QUALIFYING_PATTERNS
    ]
    if qualifying:
        result.klass = "declared"
    elif result.content_hint or result.filename_year:
        result.klass = "inferred"

    result.effect_dates = _distinct_effect_dates(text)
    return result


EFFECT_PHRASE_RE = re.compile(
    r"\b(?:w\s*\.\s*e\s*\.\s*f\.?|with effect from|effective from|"
    r"came into force|came into effect)\b",
    re.IGNORECASE,
)


def _distinct_effect_dates(text: str) -> list[str]:
    dates: list[str] = []
    for match in EFFECT_PHRASE_RE.finditer(text):
        segment = text[match.end() : match.end() + 40]
        found = DATE_RE.search(segment)
        if found:
            dates.append(found.group(0).strip())
    # preserve order, drop duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for date in dates:
        key = date.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(date)
    return ordered


def iter_docs() -> list[tuple[str, Path]]:
    docs: list[tuple[str, Path]] = []
    for directory in CORPUS_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            docs.append((path.relative_to(ROOT).as_posix(), path))
    return docs


def catalog_last_verified() -> dict[str, str]:
    if not CATALOG.is_file():
        return {}
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    out: dict[str, str] = {}
    for record in records:
        source = record.get("source_file")
        if source:
            out[str(source).replace("\\", "/")] = str(record.get("last_verified", ""))
    return out


def pdf_cache_summary() -> dict:
    if not PDF_CACHE.is_dir():
        return {"present": False, "count": 0, "oldest": None, "newest": None}
    files = [p for p in PDF_CACHE.glob("*.pdf")]
    if not files:
        return {"present": True, "count": 0, "oldest": None, "newest": None}
    stamps = sorted(p.stat().st_mtime for p in files)
    return {
        "present": True,
        "count": len(files),
        "oldest": datetime.fromtimestamp(stamps[0], tz=timezone.utc).isoformat(),
        "newest": datetime.fromtimestamp(stamps[-1], tz=timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument(
        "--count-mtime",
        action="store_true",
        help="degenerate mode: treat every file's mtime as an inferred signal",
    )
    parser.add_argument(
        "--list-declared",
        action="store_true",
        help="print each declared document and the clause pattern(s) it matched",
    )
    args = parser.parse_args(argv)

    catalog = catalog_last_verified()
    docs = iter_docs()

    results: list[DocResult] = []
    per_dir: dict[str, dict[str, int]] = {d: {"declared": 0, "inferred": 0, "none": 0}
                                          for d in CORPUS_DIRS}
    pattern_counts: dict[str, int] = {name: 0 for name in DECLARED_PATTERNS}
    raw_pattern_counts: dict[str, int] = {name: 0 for name in DECLARED_PATTERNS}
    mt = []

    for rel, path in docs:
        text = path.read_text(encoding="utf-8", errors="replace")
        result = classify(text, rel)
        if rel in catalog and not result.content_hint:
            result.content_hint = True
            if result.klass == "none":
                result.klass = "inferred"
        if args.count_mtime and result.klass == "none":
            result.klass = "inferred"
        result.mtime = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        mt.append(path.stat().st_mtime)
        results.append(result)

        top = "/".join(rel.split("/")[:2]) if rel.startswith("data/") else "other"
        if top in per_dir:
            per_dir[top][result.klass] += 1
        for name in result.declared_matches:
            pattern_counts[name] += 1
        for name, pattern in DECLARED_PATTERNS.items():
            if pattern.search(text):
                raw_pattern_counts[name] += 1

    counts = {
        "declared": sum(1 for r in results if r.klass == "declared"),
        "inferred": sum(1 for r in results if r.klass == "inferred"),
        "none": sum(1 for r in results if r.klass == "none"),
    }
    total = len(results)

    before_after = sorted(
        (
            {
                "path": r.rel_path,
                "class": r.klass,
                "distinct_effect_dates": len(r.effect_dates),
                "dates": r.effect_dates,
            }
            for r in results
            if len(r.effect_dates) >= MIN_EFFECT_DATES
        ),
        key=lambda item: (-item["distinct_effect_dates"], item["path"]),
    )

    central = []
    for rel in CENTRAL_SCHEMES:
        match = next((r for r in results if r.rel_path == rel), None)
        if match is None:
            continue
        central.append(
            {
                "path": rel,
                "class": match.klass,
                "amendment_or_effect_language": sorted(match.declared_matches),
                "recorded_date_hint": match.content_hint,
            }
        )

    evidence: dict[str, list[dict[str, str]]] = {
        name: [] for name in DECLARED_PATTERNS
    }
    for r in results:
        for name, snippets in r.declared_matches.items():
            if snippets:
                evidence[name].append({"path": r.rel_path, "match": snippets[0]})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_documents": total,
        "counts": counts,
        "per_directory": per_dir,
        "declared_pattern_file_counts": pattern_counts,
        "raw_pattern_file_counts": raw_pattern_counts,
        "pattern_definitions": {
            name: pattern.pattern for name, pattern in DECLARED_PATTERNS.items()
        },
        "date_regex": DATE_RE.pattern,
        "window_chars": WINDOW,
        "mtime_range": {
            "present": bool(mt),
            "count": len(mt),
            "oldest": datetime.fromtimestamp(min(mt), tz=timezone.utc).isoformat()
            if mt
            else None,
            "newest": datetime.fromtimestamp(max(mt), tz=timezone.utc).isoformat()
            if mt
            else None,
        },
        "count_mtime_mode": args.count_mtime,
        "pdf_cache": pdf_cache_summary(),
        "catalog_records": len(catalog),
        "central_schemes": central,
        "before_after_candidates": before_after,
        "evidence_examples": {
            name: entries[:5] for name, entries in evidence.items() if entries
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.list_declared:
        for r in results:
            if r.klass == "declared":
                print(f"{r.rel_path}\t{','.join(sorted(r.declared_matches))}")
        return 0

    print(f"total documents: {total}")
    print(
        f"declared: {counts['declared']}  "
        f"inferred: {counts['inferred']}  none: {counts['none']}"
    )
    print("  by directory:")
    for directory, tally in per_dir.items():
        print(
            f"    {directory}: declared={tally['declared']} "
            f"inferred={tally['inferred']} none={tally['none']}"
        )
    print("declared pattern file counts (date-qualified / phrase-present):")
    for name, count in pattern_counts.items():
        print(f"    {name}: {count} / {raw_pattern_counts[name]}")
    print(f"mtime range ({len(mt)} files): {payload['mtime_range']['oldest']} .. "
          f"{payload['mtime_range']['newest']}")
    print(f"pdf cache: {payload['pdf_cache']['count']} file(s)")
    print(f"before/after candidates (>= {MIN_EFFECT_DATES} distinct effect dates): "
          f"{len(before_after)}")
    for item in before_after[:10]:
        print(f"    {item['path']}: {item['distinct_effect_dates']} -> "
              f"{', '.join(item['dates'][:6])}")
    print("central schemes:")
    for item in central:
        print(f"    {item['path']}: class={item['class']} "
              f"amendment_language={item['amendment_or_effect_language'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
