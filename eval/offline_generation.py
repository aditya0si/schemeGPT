"""Offline generation metrics over an archived live-run capture.

This module scores the answers in ``eval/fixtures/generation_snapshot.jsonl``
using only pure functions from :mod:`app.quotes`. It makes no network call,
needs no API key, and imports no retriever, database, or LLM client, so it runs
with ``GROQ_API_KEY`` explicitly empty -- see
``.github/workflows/offline-generation.yml``. The provider credential that the
live generation harness needs is irrelevant here.

Two measurements are reported per case and in aggregate:

``quote_metrics``
    Parse the answer's structured ``> ... [source, status]`` quote lines and
    count how many quoted texts appear verbatim (normalised) in the retrieved
    source chunks. This is *grounding*: it proves the quoted words are an exact
    substring of a retrieved source. It deliberately ignores which source the
    model named; attribution is a separate question.

``citation_metrics``
    Citation *coverage*: the share of cases whose answer carries at least one
    structured citation. It also reports attribution (whether the cited source
    name resolves to a retrieved source and the quote verifies against it), but
    that figure is not gated because the archived capture predates the current
    citation-label contract.

The archived fixture is a live-run capture dated 2026-09-01, but that first
capture is degenerate: 7 of its 8 cases are demo fallbacks with no retrieved
sources, and the archive does not record why they fell back. Only case 0
(``pmjay-cover``) is a real live answer. Case 0's ``error`` records an
authenticated-org throttle (``RateLimitError`` HTTP 429 on tokens per day), so
the credential authenticated that day and a rejected credential must not be
inferred. The aggregate rates therefore sit over a denominator that mostly
cannot ground a quote; they are regression tripwires, **not** generation-quality
signals, and this document must not be read as a quality baseline.

Floors -- **PROVISIONAL**, derived from the degenerate first measurement and to
be re-derived after the first valid capture (set below the first measurement,
never at or above it):

* ``QUOTE_VERIFICATION_FLOOR = 0.40`` -- measured 0.50 (1 verified quote of 2;
  the other quote line is a stray ``>`` inside a demo fallback). Margin 0.10.
* ``CITATION_COVERAGE_FLOOR = 0.20`` -- measured 0.25 (2 of 8 cases cited; the
  other 7 are demo fallbacks). Margin 0.05.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.quotes import ParsedQuote, parse_quotes, verify_quotes

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE = EVAL_DIR / "fixtures" / "generation_snapshot.jsonl"
RESULTS_FILE = EVAL_DIR / "results" / "generation_offline_scores.json"

QUOTE_VERIFICATION_FLOOR = 0.40
CITATION_COVERAGE_FLOOR = 0.20

# Provenance counts for the degenerate archived capture. They are quoted
# verbatim in ``docs/evidence/OFFLINE-GENERATION.md`` and asserted against the
# committed fixture in ``tests/test_offline_generation.py``, so the document
# cannot silently disagree with the artifact it describes.
ARCHIVE_GROUNDED_CASES = 1
ARCHIVE_QUOTE_LINES = 2

REQUIRED_RECORD_KEYS = ("id", "question", "answer", "sources")


def load_fixture(path: Path | None = None) -> tuple[dict, list[dict]]:
    """Load the JSONL fixture, returning ``(header, records)``.

    The first ``header`` record is optional metadata; every remaining line must
    carry the required case keys. A fixture with zero cases is an error: there
    is nothing to measure.
    """
    fixture = Path(path) if path is not None else DEFAULT_FIXTURE
    if not fixture.is_file():
        raise FileNotFoundError(f"generation fixture not found: {fixture}")

    header: dict = {}
    records: list[dict] = []
    for line_number, line in enumerate(
        fixture.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{fixture.as_posix()}:{line_number}: invalid JSON: {exc}"
            ) from exc
        if obj.get("type") == "header":
            header = obj
            continue
        missing = [key for key in REQUIRED_RECORD_KEYS if key not in obj]
        if missing:
            raise ValueError(
                f"{fixture.as_posix()}:{line_number}: missing keys {missing}"
            )
        records.append(obj)

    if not records:
        raise ValueError(
            f"{fixture.as_posix()} has zero cases; refusing to evaluate an empty "
            "fixture"
        )
    return header, records


def _ground_quote(quote: ParsedQuote, sources: list[dict]) -> bool:
    """True when the quote text is an exact substring of any retrieved source.

    The model's own source label is intentionally not consulted here: a real
    quote attached to a wrong label is still grounded text. Candidate quotes are
    rebuilt with each retrieved source's own name and status so
    :func:`app.quotes.verify_quotes` performs its exact-substring matching
    against that source.
    """
    candidates = [
        ParsedQuote(
            text=quote.text,
            source=str(source.get("source", "")),
            status=source.get("data_status"),
        )
        for source in sources
    ]
    if not candidates:
        return False
    return any(result.verified for result in verify_quotes(candidates, sources))


def quote_metrics(answer: str, sources: list[dict]) -> dict:
    """Grounding metrics for one answer's structured quote lines."""
    parsed = parse_quotes(answer or "")
    verified = sum(1 for quote in parsed if _ground_quote(quote, sources or []))
    return {
        "quotes": len(parsed),
        "verified_quotes": verified,
        "verification_rate": verified / len(parsed) if parsed else None,
    }


def citation_metrics(answer: str, sources: list[dict]) -> dict:
    """Citation coverage and attribution for one answer."""
    parsed = parse_quotes(answer or "")
    verified = verify_quotes(parsed, sources or [])
    attributed = sum(1 for quote in verified if quote.verified)
    return {
        "citations": len(parsed),
        "attributed_citations": attributed,
        "attribution_rate": attributed / len(parsed) if parsed else None,
        "cited": 1 if parsed else 0,
    }


def evaluate(records: list[dict]) -> dict:
    """Aggregate quote and citation metrics over fixture records."""
    rows: list[dict] = []
    total_quotes = 0
    total_verified = 0
    total_citations = 0
    total_attributed = 0
    cited_cases = 0

    for index, record in enumerate(records, start=1):
        quotes = quote_metrics(record.get("answer", ""), record.get("sources") or [])
        citations = citation_metrics(
            record.get("answer", ""), record.get("sources") or []
        )
        total_quotes += quotes["quotes"]
        total_verified += quotes["verified_quotes"]
        total_citations += citations["citations"]
        total_attributed += citations["attributed_citations"]
        cited_cases += citations["cited"]
        rows.append(
            {
                "id": record.get("id") or f"case-{index}",
                "question": record.get("question", ""),
                "sources": len(record.get("sources") or []),
                "quotes": quotes["quotes"],
                "verified_quotes": quotes["verified_quotes"],
                "verification_rate": quotes["verification_rate"],
                "citations": citations["citations"],
                "attributed_citations": citations["attributed_citations"],
            }
        )

    cases = len(records)
    return {
        "cases": cases,
        "cases_with_quotes": sum(1 for row in rows if row["quotes"]),
        "cases_with_citations": cited_cases,
        "quotes": total_quotes,
        "verified_quotes": total_verified,
        "quote_verification_rate": (
            total_verified / total_quotes if total_quotes else None
        ),
        "citation_coverage": cited_cases / cases if cases else None,
        "attributed_citations": total_attributed,
        "citation_attribution_rate": (
            total_attributed / total_citations if total_citations else None
        ),
        "rows": rows,
    }


def gate_failures(summary: dict) -> list[str]:
    """Return the floor breaches for an aggregate summary."""
    failures: list[str] = []
    cases = int(summary.get("cases") or 0)
    if cases == 0:
        failures.append("cases: fixture has no cases")
    for name, floor in (
        ("quote_verification_rate", QUOTE_VERIFICATION_FLOOR),
        ("citation_coverage", CITATION_COVERAGE_FLOOR),
    ):
        value = summary.get(name)
        if value is None:
            failures.append(f"{name}: missing")
        elif float(value) < floor:
            failures.append(f"{name}: {float(value):.3f} < {floor:.2f}")
    return failures


def run(
    fixture: Path | None = None,
    output: Path | None = None,
) -> tuple[dict, list[str]]:
    # Resolve module constants at CALL time, never bind them as default
    # arguments: a default argument is evaluated once at import, so redirecting
    # the path (tests, tooling) would silently keep writing the real artifact.
    fixture = Path(fixture) if fixture is not None else DEFAULT_FIXTURE
    output = Path(output) if output is not None else RESULTS_FILE

    header, records = load_fixture(fixture)
    summary = evaluate(records)
    summary["fixture"] = fixture.as_posix()
    summary["provenance"] = header
    failures = gate_failures(summary)
    summary["gate"] = {
        "passed": not failures,
        "failures": failures,
        "floors": {
            "quote_verification_rate": QUOTE_VERIFICATION_FLOOR,
            "citation_coverage": CITATION_COVERAGE_FLOOR,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score an archived generation fixture with no key or network."
    )
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        summary, failures = run(args.fixture, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"OFFLINE GENERATION FAILED: {exc}", file=sys.stderr)
        return 1

    rate = summary["quote_verification_rate"]
    coverage = summary["citation_coverage"]
    print(
        f"Offline generation: {summary['cases']} case(s), "
        f"quotes={summary['verified_quotes']}/{summary['quotes']} "
        f"(verification_rate={rate}), cases_with_citations={summary['cases_with_citations']} "
        f"(citation_coverage={coverage})"
    )
    if failures:
        for failure in failures:
            print(f"OFFLINE GENERATION FAILED: {failure}")
        return 1
    print(f"Floors passed. Results: {(Path(args.output) if args.output else RESULTS_FILE).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
