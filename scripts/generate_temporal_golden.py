"""Derive the temporal golden set from the frozen dated-claims artifact.

Phase 8 / track 1, **Task 3**. The golden set is **derived, never hand-written**:
this script reads ``eval/fixtures/temporal_claims.jsonl`` (the Task 1 artifact),
groups its claims into ladders by source, and emits one case per interesting
date for every rung of every ladder. Every expectation (the value in force, its
effective date, the replacement, and whether the answer must refuse) is computed
from the artifact itself and recorded in ``derived_from`` so it can be audited
back to the exact claim ids that produced it.

Cases, per ladder (``F`` is a claim's effective date):

* ``effective_date`` -- ``as_of == F``: the NEW value applies (inclusive).
* ``day_before``     -- ``as_of == F - 1 day``: the PREVIOUS value applies.
* ``inside_range``   -- ``as_of == F + 1 day`` (only when a successor exists):
  the value is in force across its whole interval.
* ``after_last``     -- ``as_of == last.F + 1 day``: the latest value, with no
  invented successor.
* ``before_first``   -- ``as_of == first.F - 1 day``: must refuse.
* ``unmatched``      -- a question naming no ladder: must refuse.

The output is JSONL: a leading header line, then one sorted record per case. It
is stdlib-only, offline, and read-only apart from writing the fixture.

Usage::

    ./.venv/Scripts/python.exe scripts/generate_temporal_golden.py
    ./.venv/Scripts/python.exe scripts/generate_temporal_golden.py --check
    ./.venv/Scripts/python.exe scripts/generate_temporal_golden.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CLAIMS_FIXTURE = ROOT / "eval" / "fixtures" / "temporal_claims.jsonl"
DEFAULT_OUTPUT = ROOT / "eval" / "fixtures" / "temporal_golden.jsonl"
GENERATOR = "scripts/generate_temporal_golden.py"

# A question that names no ladder. The trailing nonsense token guarantees no
# filename-stem match, so the case must refuse as unmatched.
UNMATCHED_QUESTION = "no-such-ladder-zzqqxxyy"

# Deterministic case ordering. Lower rank sorts first within a ladder.
_KIND_ORDER = {
    "effective_date": 0,
    "day_before": 1,
    "inside_range": 2,
    "after_last": 3,
    "before_first": 4,
    "unmatched": 5,
}


def _stem(source: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(source).stem.casefold())


def load_artifact(path: Path | None = None) -> tuple[dict, list[dict]]:
    """Read the dated-claims JSONL artifact into ``(header, claims)``."""
    source = Path(path) if path is not None else CLAIMS_FIXTURE
    lines = [
        line for line in source.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not lines:
        raise ValueError(f"{source.as_posix()} is empty")
    header = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:]]
    claims = [record for record in records if record.get("type") != "header"]
    if not claims:
        raise ValueError(f"{source.as_posix()} contains zero claims")
    return header, claims


def _group_ladders(claims: list[dict]) -> dict[str, list[dict]]:
    ladders: dict[str, list[dict]] = {}
    for claim in claims:
        ladders.setdefault(str(claim["source"]), []).append(claim)
    for ladder in ladders.values():
        ladder.sort(key=lambda claim: (claim["effective_from"], claim["claim_id"]))
    return ladders


def _case(
    *,
    source: str | None,
    kind: str,
    as_of: date,
    expect: str,
    question: str,
    governing: dict | None = None,
    successor: dict | None = None,
    refusal_reason: str | None = None,
    derived_from: list[str] | None = None,
) -> dict:
    stem = _stem(source) if source is not None else "unmatched"
    case_id = f"{stem}#{kind}#{as_of.isoformat()}"
    return {
        "id": case_id,
        "kind": kind,
        "source": source,
        "question": question,
        "as_of": as_of.isoformat(),
        "expect": expect,
        "refusal_reason": refusal_reason,
        "governing_claim_id": governing["claim_id"] if governing else None,
        "expected_value": governing["value"] if governing else None,
        "expected_effective_from": (
            governing["effective_from"] if governing else None
        ),
        "successor_claim_id": successor["claim_id"] if successor else None,
        "successor_value": successor["value"] if successor else None,
        "successor_effective_from": (
            successor["effective_from"] if successor else None
        ),
        "derived_from": derived_from or [],
    }


def build_golden(artifact_path: Path | None = None) -> tuple[dict, list[dict]]:
    """Build ``(header, records)`` for the golden set from the artifact."""
    artifact_header, claims = load_artifact(artifact_path)
    ladders = _group_ladders(claims)
    cases: list[dict] = []

    for source in sorted(ladders):
        ladder = ladders[source]
        question = _stem(source)
        for index, claim in enumerate(ladder):
            effective = date.fromisoformat(claim["effective_from"])
            successor = ladder[index + 1] if index + 1 < len(ladder) else None
            # (a) the effective date itself: the NEW value applies.
            cases.append(
                _case(
                    source=source,
                    kind="effective_date",
                    as_of=effective,
                    expect="answer",
                    question=question,
                    governing=claim,
                    successor=successor,
                    derived_from=[claim["claim_id"]]
                    + ([successor["claim_id"]] if successor else []),
                )
            )
            if index > 0:
                previous = ladder[index - 1]
                # (b) the day before: the PREVIOUS value applies.
                cases.append(
                    _case(
                        source=source,
                        kind="day_before",
                        as_of=effective - timedelta(days=1),
                        expect="answer",
                        question=question,
                        governing=previous,
                        successor=claim,
                        derived_from=[previous["claim_id"], claim["claim_id"]],
                    )
                )
            else:
                # (e) before the first effective date: must refuse.
                cases.append(
                    _case(
                        source=source,
                        kind="before_first",
                        as_of=effective - timedelta(days=1),
                        expect="refuse",
                        question=question,
                        refusal_reason="before",
                        derived_from=[claim["claim_id"]],
                    )
                )
            if successor is not None:
                # (c) a date strictly inside the range.
                cases.append(
                    _case(
                        source=source,
                        kind="inside_range",
                        as_of=effective + timedelta(days=1),
                        expect="answer",
                        question=question,
                        governing=claim,
                        successor=successor,
                        derived_from=[claim["claim_id"], successor["claim_id"]],
                    )
                )
        # (d) after the last value: the latest value, no invented successor.
        last = ladder[-1]
        cases.append(
            _case(
                source=source,
                kind="after_last",
                as_of=date.fromisoformat(last["effective_from"]) + timedelta(days=1),
                expect="answer",
                question=question,
                governing=last,
                successor=None,
                derived_from=[last["claim_id"]],
            )
        )

    # (f) a question naming no ladder: must refuse.
    earliest = min(claims, key=lambda claim: claim["effective_from"])
    cases.append(
        _case(
            source=None,
            kind="unmatched",
            as_of=date.fromisoformat(earliest["effective_from"]),
            expect="refuse",
            question=UNMATCHED_QUESTION,
            refusal_reason="unmatched",
            derived_from=[earliest["claim_id"]],
        )
    )

    cases.sort(
        key=lambda case: (
            case["source"] or "~",
            _KIND_ORDER[case["kind"]],
            case["as_of"],
            case["id"],
        )
    )
    kinds: dict[str, int] = {}
    for case in cases:
        kinds[case["kind"]] = kinds.get(case["kind"], 0) + 1
    header = {
        "type": "header",
        "generator": GENERATOR,
        "artifact": "eval/fixtures/temporal_claims.jsonl",
        "artifact_claims": len(claims),
        "artifact_documents": artifact_header.get("documents"),
        "ladders": len(ladders),
        "cases": len(cases),
        "kinds": kinds,
    }
    return header, cases


def serialise(header: dict, records: list[dict]) -> str:
    """Serialise to canonical LF-terminated JSONL (sorted keys, UTF-8 safe)."""
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    lines += [
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
    ]
    return "\n".join(lines) + "\n"


def write_golden(header: dict, records: list[dict], output: Path) -> int:
    """Write the golden fixture, refusing to write an empty one."""
    if not records:
        raise ValueError("refusing to write a golden set with zero cases")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(serialise(header, records).encode("utf-8"))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed golden set byte-for-byte with a fresh "
        "derivation; exit non-zero on drift",
    )
    parser.add_argument("--json", action="store_true", help="emit the payload only")
    args = parser.parse_args(argv)

    header, records = build_golden()
    payload = serialise(header, records).encode("utf-8")

    if args.json:
        print(json.dumps({"header": header, "records": records}, ensure_ascii=False))
        return 0

    if args.check:
        committed = args.output.read_bytes() if args.output.is_file() else b""
        if committed == payload:
            print(
                f"golden set is current: {len(records)} case(s) from "
                f"{header['ladders']} ladder(s)"
            )
            return 0
        print(
            "GOLDEN DRIFT: committed golden set does not match a fresh "
            "derivation; regenerate with scripts/generate_temporal_golden.py",
            file=sys.stderr,
        )
        return 1

    try:
        count = write_golden(header, records, args.output)
    except ValueError as exc:
        print(f"GOLDEN GENERATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {count} golden case(s) from {header['ladders']} ladder(s) to "
        f"{args.output.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
