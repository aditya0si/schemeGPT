"""Extract effective-dated claims from the corpus and freeze them to a fixture.

The parser lives in :mod:`app.temporal`; this script only walks the Markdown
corpus, calls the parser on each document, and writes the result as one JSONL
record per claim (with a leading header line) to
``eval/fixtures/temporal_claims.jsonl``. It is stdlib-only, offline, and reads
the corpus read-only.

A document whose ladder violates the never-guess rule -- dates that are not
strictly increasing in the order they appear -- is reported in the header's
``ladder_problems`` list and contributes no claims; it is never reordered.

Usage::

    ./.venv/Scripts/python.exe scripts/extract_temporal_claims.py
    ./.venv/Scripts/python.exe scripts/extract_temporal_claims.py --check
    ./.venv/Scripts/python.exe scripts/extract_temporal_claims.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.temporal import TemporalLadderError, extract_claims  # noqa: E402

CORPUS_DIRS = ("data/myscheme", "data/schemes", "data/states")
DEFAULT_OUTPUT = ROOT / "eval" / "fixtures" / "temporal_claims.jsonl"
GENERATOR = "scripts/extract_temporal_claims.py"


def iter_documents() -> list[tuple[str, Path]]:
    """Return ``(relative_path, path)`` for every corpus Markdown document."""
    documents: list[tuple[str, Path]] = []
    for directory in CORPUS_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            documents.append((path.relative_to(ROOT).as_posix(), path))
    return documents


def build_claims() -> tuple[dict, list[dict]]:
    """Run the extraction over the corpus and return ``(header, records)``."""
    documents = iter_documents()
    records: list[dict] = []
    problems: list[dict] = []
    sources_with_claims: set[str] = set()
    for relative, path in documents:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            claims = extract_claims(text, relative)
        except TemporalLadderError as exc:
            problems.append({"source": relative, "error": str(exc)})
            continue
        if claims:
            sources_with_claims.add(relative)
        records.extend(claim.to_dict() for claim in claims)

    records.sort(
        key=lambda record: (
            record["source"],
            record["effective_from"],
            record["claim_id"],
        )
    )
    header = {
        "type": "header",
        "generator": GENERATOR,
        "corpus_dirs": list(CORPUS_DIRS),
        "documents": len(documents),
        "claims": len(records),
        "sources_with_claims": len(sources_with_claims),
        "ladder_problems": problems,
    }
    return header, records


def _serialise(header: dict, records: list[dict]) -> str:
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    lines += [
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
    ]
    return "\n".join(lines) + "\n"


def write_fixture(header: dict, records: list[dict], output: Path) -> int:
    """Write the JSONL fixture, refusing to write an empty one."""
    if not records:
        raise ValueError("refusing to write a fixture with zero claims")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_serialise(header, records).encode("utf-8"))
    return len(records)


def load_fixture(path: Path | None = None) -> tuple[dict, list[dict]]:
    """Load a JSONL fixture into ``(header, records)``."""
    source = Path(path) if path is not None else DEFAULT_OUTPUT
    if not source.is_file():
        return {}, []
    lines = [
        line for line in source.read_text(encoding="utf-8").splitlines() if line
    ]
    if not lines:
        return {}, []
    header = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:]]
    if not records:
        raise ValueError("fixture contains zero claims")
    return header, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed fixture with a fresh extraction; exit "
        "non-zero on drift",
    )
    parser.add_argument("--json", action="store_true", help="emit the payload only")
    args = parser.parse_args(argv)

    header, records = build_claims()

    if args.json:
        print(json.dumps({"header": header, "records": records}, ensure_ascii=False))
        return 0

    if args.check:
        committed_header, committed = load_fixture(args.output)
        if committed == records and committed_header.get("claims") == header["claims"]:
            print(
                f"fixture is current: {len(records)} claim(s) from "
                f"{header['sources_with_claims']} source(s)"
            )
            return 0
        print(
            "FIXTURE DRIFT: committed fixture does not match a fresh "
            "extraction; regenerate with "
            "scripts/extract_temporal_claims.py",
            file=sys.stderr,
        )
        return 1

    try:
        count = write_fixture(header, records, args.output)
    except ValueError as exc:
        print(f"EXTRACTION FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {count} claim(s) from {header['sources_with_claims']} source(s) "
        f"to {args.output.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
