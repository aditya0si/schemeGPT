"""The unit suite must not open a live database connection.

CI's ``tests`` job runs ``python -m pytest -q`` under the comment "no DB, no
Groq, no model downloads", and every database-touching test injects a fake
engine -- but until this file nothing enforced it. A unit test reached, for real:

    app.rag.answer -> app.semantic_cache.capture_generation
                   -> app.db.read_corpus_generation -> engine.connect()

using the default DSN from ``app/config.py``
(``postgresql+psycopg://scheme:scheme@localhost:5432/schemegpt``). CI has no
server on 5432, so the connect was refused and the test passed through the
failure branch it was written around; this host silently drops loopback
connects, so the same call blocked the run inside ``psycopg/waiting.py::
wait_conn`` for minutes. The isolation defect was real on both hosts and
observable on only one.

``tests/conftest.py`` installs the blocker, and the per-test guard there means
every test in the suite is now also a proof (any attempt fails the test that
made it). The tests here prove the guard itself is armed, is not vacuous, and
turns the historical call chain into an immediate, named failure.
"""

from __future__ import annotations

import time

import pytest

from app import db

# The default DSN app/config.py ships. It is a documented local development
# credential, not a secret, and no connection is ever completed with it here.
DEFAULT_DSN = "postgresql://scheme:scheme@localhost:5432/schemegpt"

GUARD_MESSAGE = "test isolation violation"


def _drain(attempts: list[str]) -> list[str]:
    """Take the records so far and reset the list.

    These tests provoke the blocker on purpose, so they own their records:
    without this the per-test guard in ``tests/conftest.py`` would fail the test
    that is busy checking the guard.
    """
    made = list(attempts)
    del attempts[:]
    return made


def test_guard_is_armed_for_the_sync_driver(live_database_attempts):
    import psycopg

    with pytest.raises(AssertionError, match=GUARD_MESSAGE):
        psycopg.connect(DEFAULT_DSN)

    made = _drain(live_database_attempts)
    assert made, "the blocker raised without recording the attempt"
    assert "test_no_live_database.py" in made[0]


def test_guard_is_armed_for_the_async_driver(live_database_attempts):
    import psycopg

    with pytest.raises(AssertionError, match=GUARD_MESSAGE):
        psycopg.AsyncConnection.connect(DEFAULT_DSN)

    made = _drain(live_database_attempts)
    assert made, "the blocker raised without recording the attempt"


def test_guard_covers_the_engine_the_app_configures(live_database_attempts):
    """`db.get_engine()` is the exact construction the app uses to connect."""
    started = time.monotonic()
    with pytest.raises(AssertionError, match=GUARD_MESSAGE):
        db.get_engine().connect()
    elapsed = time.monotonic() - started

    made = _drain(live_database_attempts)
    assert made, "the blocker raised without recording the attempt"
    assert elapsed < 5.0, "the guard must fail immediately, not after a timeout"


def test_the_historical_call_chain_now_fails_fast(live_database_attempts):
    """`db.read_corpus_generation` is the frame from the blocking traceback.

    Before the guard this call blocked for minutes on this host (`wait_conn`
    under `engine.connect()`); now it fails in milliseconds, and the attempt is
    recorded so the failure cannot be mistaken for a closed database.
    """
    started = time.monotonic()
    with pytest.raises(db.CorpusMetadataError) as caught:
        db.read_corpus_generation()
    elapsed = time.monotonic() - started

    made = _drain(live_database_attempts)
    assert made, "read_corpus_generation failed without attempting a connection"
    assert GUARD_MESSAGE in str(caught.value.__cause__ or "")
    assert elapsed < 5.0, "the guard must fail immediately, not after a timeout"
