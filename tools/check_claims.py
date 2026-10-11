"""Fail when README's recorded counts drift from the repository.

``README.md`` carries one machine-readable block:

    <!-- claims: tests=<collected test count> evidence=<tracked evidence files> -->

The numbers are recomputed here -- collected tests via ``pytest --collect-only``
and evidence files via ``git ls-files`` over the guarded paths -- and any
mismatch exits non-zero. Update the block only after the change that made it
stale is committed; never hand-edit the numbers to silence the checker.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import evidence_manifest as em  # noqa: E402  (needs ROOT on sys.path)

README = ROOT / "README.md"

CLAIMS_RE = re.compile(r"<!--\s*claims:\s*(?P<body>.*?)-->", re.DOTALL)
TESTS_RE = re.compile(r"tests\s*=\s*(\d+)")
EVIDENCE_RE = re.compile(r"evidence\s*=\s*(\d+)")
COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")


def declared_claims(readme: str) -> tuple[int, int]:
    match = CLAIMS_RE.search(readme)
    if not match:
        raise ValueError("no `<!-- claims: ... -->` block found in README.md")
    body = match.group("body")
    tests = TESTS_RE.search(body)
    evidence = EVIDENCE_RE.search(body)
    if not tests or not evidence:
        raise ValueError(
            "claims block must contain `tests=<N>` and `evidence=<N>`: "
            f"{body.strip()!r}"
        )
    return int(tests.group(1)), int(evidence.group(1))


def collected_test_count() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    matches = COLLECTED_RE.findall(result.stdout + result.stderr)
    if not matches:
        raise RuntimeError(
            "could not determine the collected test count from pytest:\n"
            + (result.stdout + result.stderr)[-2000:]
        )
    return int(matches[-1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    actual_tests = collected_test_count()
    actual_evidence = len(em.tracked_files())
    try:
        declared_tests, declared_evidence = declared_claims(
            README.read_text(encoding="utf-8")
        )
    except ValueError as exc:
        print(f"CLAIMS FAILED: {exc}", file=sys.stderr)
        return 1

    drift: list[str] = []
    if declared_tests != actual_tests:
        drift.append(f"tests: README says {declared_tests}, repo has {actual_tests}")
    if declared_evidence != actual_evidence:
        drift.append(
            f"evidence: README says {declared_evidence}, repo has {actual_evidence}"
        )
    if drift:
        for line in drift:
            print(f"CLAIMS FAILED: {line}", file=sys.stderr)
        print(
            "Update the `<!-- claims: ... -->` block in README.md to the "
            "measured counts.",
            file=sys.stderr,
        )
        return 1

    print(f"claims ok: tests={actual_tests} evidence={actual_evidence}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
