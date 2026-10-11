"""Freeze and verify the repository's committed evidence.

The *evidence paths* are the directories that hold published, measured
artifacts:

    eval/results/          publishable evaluation reports
    docs/evidence/         measured drill / retrieval-gate write-ups
    deploy/field/reports/  raw field-rehearsal JSON records
    loadtest/              load-test script and measured results

Every git-tracked file under those paths is hashed with ``sha256[:16]`` and
recorded in ``evidence/manifest.json``. The drift test
(``tests/test_evidence_guards.py``) fails if any recorded byte changes, and the
session canary in ``tests/conftest.py`` fails the whole run if the tracked set
changes underneath it. Rebaselining is deliberately explicit:

    python tools/evidence_manifest.py --write

Never edit a published figure to make the guard pass; re-measure, then
rebaseline, and say so in the commit message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = ROOT / "evidence" / "manifest.json"

# The guarded evidence paths. `git ls-files` is the enumeration source so the
# manifest covers exactly what is committed -- no more, no less.
EVIDENCE_PATHS = (
    "eval/results",
    "docs/evidence",
    "deploy/field/reports",
    "loadtest",
)

REBASELINE_COMMAND = "python tools/evidence_manifest.py --write"


def tracked_files() -> list[str]:
    """Git-tracked files under the evidence paths (forward-slash, sorted)."""
    result = subprocess.run(
        ["git", "ls-files", "--", *EVIDENCE_PATHS],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def _sha256_16(path: Path) -> str:
    # Hash canonical (LF) bytes so the manifest is identical on every platform.
    # `core.autocrlf=true` gives Windows a CRLF checkout of files whose
    # .gitattributes entry does not pin eol, which would otherwise make the
    # committed manifest fail on Linux CI.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:16]


def compute_manifest() -> dict[str, str]:
    """Current ``{relative_path: sha256[:16]}`` for every tracked evidence file."""
    return {relpath: _sha256_16(ROOT / relpath) for relpath in tracked_files()}


def read_manifest() -> dict[str, str]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def write_manifest() -> dict[str, str]:
    manifest = compute_manifest()
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def unexpected_files() -> list[str]:
    """Untracked, non-ignored entries under the evidence paths.

    A scratch file dropped into a guarded directory must not survive unnoticed.
    ``git status --porcelain`` shows tracked modifications and staged additions
    too, so only ``??`` (untracked, not ignored) lines are returned.
    """
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *EVIDENCE_PATHS,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line for line in result.stdout.splitlines() if line.startswith("??")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"rebaseline {MANIFEST_FILE.relative_to(ROOT).as_posix()} from the "
        "current working tree (review the diff before committing)",
    )
    args = parser.parse_args(argv)

    if args.write:
        manifest = write_manifest()
        print(
            f"wrote {MANIFEST_FILE.relative_to(ROOT).as_posix()} "
            f"({len(manifest)} evidence file(s))"
        )
        return 0

    declared = read_manifest() if MANIFEST_FILE.is_file() else {}
    actual = compute_manifest()
    missing = sorted(set(declared) - set(actual))
    added = sorted(set(actual) - set(declared))
    drifted = sorted(
        path for path in set(declared) & set(actual) if declared[path] != actual[path]
    )
    if missing or added or drifted:
        for path in missing:
            print(f"manifest references a file that is not tracked: {path}")
        for path in added:
            print(f"tracked evidence file missing from the manifest: {path}")
        for path in drifted:
            print(
                f"drift: {path} {declared[path]} -> {actual[path]}"
            )
        print(f"rebaseline with: {REBASELINE_COMMAND}")
        return 1
    print(f"evidence manifest is current ({len(actual)} file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
