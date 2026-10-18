"""Repository-wide test guards for the published evidence.

Three independent guards protect the run:

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

* ``_no_live_database_connection`` (autouse, function-scoped) fails the test
  that reached a real Postgres driver call, so the unit suite stays the "no DB"
  suite the CI job claims it is. Its session-scoped backing fixture
  ``live_database_attempts`` is what the guard tests in
  ``tests/test_no_live_database.py`` check; the block below explains why a raise
  alone would not be enough.

See ``tools/evidence_manifest.py`` for the path list and rebaseline procedure.
"""

from __future__ import annotations

import sys
import traceback
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


# --- live-database guard ------------------------------------------------------
#
# The `tests` job in .github/workflows/ci.yml runs `python -m pytest -q` under
# the comment "no DB, no Groq, no model downloads", and every database-touching
# test injects a fake engine -- but nothing enforced that. A unit test therefore
# dialled the default DSN from app/config.py
# (`postgresql+psycopg://scheme:scheme@localhost:5432/schemegpt`) for real:
#
#     app.rag.answer -> app.semantic_cache.capture_generation
#                    -> app.db.read_corpus_generation -> engine.connect()
#
# On CI nothing listens on 5432, so the connect was refused and the test passed
# by way of the failure branch it was written around. On a host that silently
# drops loopback connects instead of refusing them, the same call blocked the
# whole run inside psycopg/waiting.py::wait_conn (measured here: still blocked
# after two minutes, against 10.2 s with connect_timeout=5). The isolation
# defect was real on both hosts; only one host could show it. A unit suite that
# passes because a database happens to be absent is not isolated, it is lucky.
#
# The blocker replaces the Postgres driver entry points with a call that records
# the attempt AND raises. Recording matters as much as raising: application code
# deliberately swallows database errors on some paths (see the corpus-generation
# read in app/rag.py, which turns a metadata failure into either a demo answer
# or a cache-less degraded answer), so a bare raise can be absorbed and the
# offending test would still pass. The function-scoped fixture below fails
# whichever test made the attempt, whatever the application did with the
# exception.

LIVE_DB_ATTEMPT = (
    "test isolation violation: a live Postgres connection was attempted. The "
    "unit suite runs with no database (see the `tests` job in "
    ".github/workflows/ci.yml); inject a fake engine or bind a corpus "
    "generation instead of connecting."
)

_GUARD_MODULE = Path(__file__).name


def _blame() -> str:
    """The repository frames that led to the blocked call, innermost kept."""
    frames = [
        (Path(frame.filename), frame.lineno, frame.name)
        for frame in traceback.extract_stack()[:-1]
        if str(ROOT) in frame.filename
        and Path(frame.filename).name != _GUARD_MODULE
    ]
    if not frames:
        return "no repository frame on the stack"
    culprit = next(
        (frame for frame in frames if frame[0].name.startswith("test_")), frames[0]
    )
    tail = [f"{path.name}:{lineno} in {name}" for path, lineno, name in frames[-4:]]
    culprit_text = f"{culprit[0].name}:{culprit[1]} in {culprit[2]}"
    if culprit_text not in tail:
        tail.insert(0, culprit_text)
    return " <- ".join(tail)


@pytest.fixture(scope="session")
def live_database_attempts():
    """Arm the live-connection blocker and yield the attempts it recorded.

    Session-scoped so the driver is patched once for the whole run, and shared
    by name so ``tests/test_no_live_database.py`` can prove the guard is armed
    and not vacuous (those tests drain the records they provoke on purpose).
    """
    import psycopg

    attempts: list[str] = []

    def blocked(*_args, **_kwargs):
        attempts.append(_blame())
        raise AssertionError(LIVE_DB_ATTEMPT)

    patcher = pytest.MonkeyPatch()
    # psycopg 3 is the driver app/db.py configures (`postgresql+psycopg`): the
    # module-level ``connect`` for the sync engine, and AsyncConnection.connect
    # for langchain-postgres' async PGEngine. psycopg2 is configured nowhere but
    # is importable in this environment, so block that door too.
    patcher.setattr(psycopg, "connect", blocked)
    patcher.setattr(psycopg.Connection, "connect", classmethod(blocked))
    patcher.setattr(psycopg.AsyncConnection, "connect", classmethod(blocked))
    try:
        import psycopg2
    except ImportError:
        pass
    else:
        patcher.setattr(psycopg2, "connect", blocked)
    try:
        yield attempts
    finally:
        patcher.undo()


@pytest.fixture(autouse=True)
def _no_live_database_connection(live_database_attempts):
    """Fail the test that attempted a live connection, not the next one."""
    before = len(live_database_attempts)
    yield
    made = live_database_attempts[before:]
    assert not made, f"{LIVE_DB_ATTEMPT} Attempted from: {made[0]}"
