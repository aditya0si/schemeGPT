#!/usr/bin/env python3
"""Deterministic, offline documentation link/asset check.

Two things are checked, both without network access:

1. **Repo-relative links and images resolve.** Every ``[text](path)`` and
   ``![alt](path)`` in the scanned Markdown files whose target is a relative
   path must exist on disk. A README whose hero image is an absolute URL to a
   file that is not even in the repository cannot fail this check; a README
   pointing at ``docs/screenshots/hero.png`` can.
2. **Dead deployment instructions do not come back.** Any line naming
   ``fly.dev`` must sit under a ``## Superseded`` heading in the same file, so a
   runbook can keep its history without instructing a reader to deploy to a host
   that no longer resolves (``docs/DEPLOY.md`` §"Superseded: the Fly.io path").

Absolute URLs are counted and reported but never fetched: a network check is not
deterministic and CI has no business depending on someone else's uptime. Repo
URLs that point into this repository are not verified either — the branch they
name may not be the branch you are on.

Usage::

    python tools/check_doc_links.py            # scan the default surfaces
    python tools/check_doc_links.py --all      # also scan docs/engagement, docs/superpowers
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FILES = (
    "README.md",
    "EXPERIMENTS.md",
    "docs/DEPLOY.md",
    "docs/AI-ENGINEERING.md",
    "docs/FIELD-DEPLOY.md",
    "docs/data-operations.md",
    "docs/evidence/RETRIEVAL-GATE.md",
    "docs/evidence/TEMPORAL-GATE.md",
    "docs/evidence/PII-BENCHMARK.md",
    "docs/evidence/FIELD-DRILL.md",
    "docs/evidence/OFFLINE-GENERATION.md",
    "docs/evidence/SPINE-SECOND-CLIENT.md",
)

_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "data:")


def _strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def check_file(path: Path, *, root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Return ``(problems, notes)`` for one Markdown file."""
    problems: list[str] = []
    notes: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root).as_posix()

    external = 0
    for match in _LINK_RE.finditer(text):
        raw = match.group(1).strip()
        target = _strip_anchor(raw)
        if not target:
            continue
        if target.startswith(_SKIP_PREFIXES):
            external += 1
            continue
        if target.startswith("/"):
            # Absolute path inside the site (e.g. a Next.js route); not a file.
            continue
        if not (path.parent / target).exists():
            problems.append(f"{rel}: link target does not exist: {raw}")
    notes.append(f"{rel}: {external} external link(s) not fetched (offline check)")

    superseded_at: int | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## Superseded"):
            superseded_at = lineno
        if "fly.dev" not in line or superseded_at is not None:
            continue
        # Naming a dead host in order to say it is dead is not an instruction.
        lowered = line.lower()
        if any(
            phrase in lowered
            for phrase in ("no longer resolves", "superseded", "history, not instructions")
        ):
            continue
        problems.append(
            f"{rel}:{lineno}: live deployment instruction names a dead host "
            f"(fly.dev) outside a '## Superseded' section: {line.strip()[:80]}"
        )
    return problems, notes


def scan(paths: list[Path], *, root: Path = ROOT) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    for path in paths:
        if not path.exists():
            problems.append(f"{path.relative_to(root).as_posix()}: file is missing")
            continue
        file_problems, file_notes = check_file(path, root=root)
        problems.extend(file_problems)
        notes.extend(file_notes)
    return problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="scan every docs/*.md too")
    args = parser.parse_args(argv)

    files = [ROOT / name for name in DEFAULT_FILES]
    if args.all:
        files = sorted({*files, *ROOT.glob("docs/**/*.md")})

    problems, notes = scan(files)
    for note in notes:
        print(note)
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"\nOK: {len(files)} file(s) checked, every repo-relative link resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
