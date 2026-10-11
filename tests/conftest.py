"""Repository-wide test guards for the published evidence.

Two independent guards protect the committed evidence:

* ``_redirect_evidence_writers`` (autouse, function-scoped) repoints every
  module-level writer constant at the test's ``tmp_path``, so no test -- however
  it calls the eval or field tooling -- can write into a real evidence
  directory. ``eval/retrieval_gate.py`` imports ``RESULTS_DIR`` from
  ``eval/run_eval.py`` at import time and derives its own path, so both modules
  are patched explicitly.

* ``evidence_canary`` (autouse, session-scoped) hashes every git-tracked file
  under the evidence paths at session start and compares at teardown, failing
  the session if the tracked set changed. It also fails if an untracked file
  appeared under a guarded path during the session.

See ``tools/evidence_manifest.py`` for the path list and rebaseline procedure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _redirect_evidence_writers(tmp_path, monkeypatch):
    """Point every evidence writer constant at ``tmp_path``, at call time."""
    import deploy.field.drill as drill
    import eval.pii_benchmark as pii_benchmark
    import eval.retrieval_gate as retrieval_gate
    import eval.run_eval as run_eval
    import eval.temporal_gate as temporal_gate

    results = tmp_path / "eval" / "results"
    monkeypatch.setattr(run_eval, "RESULTS_DIR", results)
    monkeypatch.setattr(run_eval, "REPORT_FILE", results / "report.md")
    monkeypatch.setattr(run_eval, "SCORES_FILE", results / "scores.json")
    monkeypatch.setattr(run_eval, "HISTORY_FILE", results / "history.jsonl")

    # retrieval_gate imported RESULTS_DIR from run_eval at import time, so
    # patching run_eval is not enough: patch its own derived constant too.
    monkeypatch.setattr(
        retrieval_gate, "RESULTS_FILE", results / "retrieval_scores.json"
    )
    monkeypatch.setattr(
        pii_benchmark, "RESULTS_FILE", results / "pii_benchmark.json"
    )
    # temporal_gate also resolves its module constants at call time.
    monkeypatch.setattr(
        temporal_gate, "RESULTS_FILE", results / "temporal_scores.json"
    )
    monkeypatch.setattr(
        temporal_gate, "REPORT_FILE", results / "temporal_report.md"
    )

    reports = tmp_path / "deploy" / "field" / "reports"
    monkeypatch.setattr(drill, "REPORTS_DIR", reports)
    monkeypatch.setattr(drill, "EVIDENCE_DIR", tmp_path / "docs" / "evidence")
    yield


@pytest.fixture(scope="session", autouse=True)
def evidence_canary():
    """Fail the session if any tracked evidence file changes while it runs."""
    from tools import evidence_manifest as em

    start_hashes = em.compute_manifest()
    start_unexpected = em.unexpected_files()

    yield

    end_hashes = em.compute_manifest()
    end_unexpected = em.unexpected_files()

    added = sorted(set(end_hashes) - set(start_hashes))
    removed = sorted(set(start_hashes) - set(end_hashes))
    changed = sorted(
        path
        for path in set(start_hashes) & set(end_hashes)
        if start_hashes[path] != end_hashes[path]
    )
    new_unexpected = sorted(set(end_unexpected) - set(start_unexpected))

    problems: list[str] = []
    if added:
        problems.append(f"tracked files added during the session: {added}")
    if removed:
        problems.append(f"tracked files removed during the session: {removed}")
    if changed:
        problems.append(f"tracked evidence files changed: {changed}")
    if new_unexpected:
        problems.append(f"untracked files appeared in guarded paths: {new_unexpected}")

    assert not problems, (
        "evidence canary failed: "
        + "; ".join(problems)
        + f". If a measurement genuinely changed, rebaseline deliberately with "
        f"`{em.REBASELINE_COMMAND}` and commit the diff."
    )
