"""Atomic, source-aware corpus ingestion contracts."""

from unittest.mock import MagicMock

import pytest

from app import ingest


def _rows():
    return [
        {
            "id": "source-aware-id",
            "content": "policy",
            "metadata": {"source": "schemes/a.md", "chunk_index": 0},
        }
    ]


class _RecordingConnection:
    """Minimal SQLAlchemy-connection stand-in that records statement order.

    Each recorded entry is ``(sql, inside_transaction)`` so a test can prove a
    statement runs inside the single activation transaction (not after it).
    """

    def __init__(self, fail_on=()):
        self.statements: list[tuple[str, bool]] = []
        self.active = False
        self.fail_on = set(fail_on)

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, self.active))
        for token in self.fail_on:
            if token in sql:
                raise RuntimeError(f"boom:{token}")
        return None


class _FakeBegin:
    def __init__(self, connection):
        self._connection = connection
        self.exc_type = None

    def __enter__(self):
        self._connection.active = True
        return self._connection

    def __exit__(self, exc_type, exc, traceback):
        self._connection.active = False
        self.exc_type = exc_type
        return False


class _FakeEngine:
    def __init__(self, connection):
        self._connection = connection
        self.begin_count = 0
        self.last_begin: _FakeBegin | None = None

    def begin(self):
        self.begin_count += 1
        self.last_begin = _FakeBegin(self._connection)
        return self.last_begin


def _install_engine(monkeypatch, connection, fail_embeddings=False):
    embeddings = MagicMock()
    if fail_embeddings:
        embeddings.embed_documents.side_effect = RuntimeError("model unavailable")
    else:
        embeddings.embed_documents.return_value = [[0.1, 0.2]]
    ensure_table = MagicMock()
    engine = _FakeEngine(connection)
    monkeypatch.setattr(ingest, "get_embeddings", lambda: embeddings)
    monkeypatch.setattr(ingest, "ensure_vector_table", ensure_table)
    monkeypatch.setattr(ingest, "get_engine", lambda: engine)
    return embeddings, ensure_table, engine


def test_chunk_id_includes_source_and_position():
    content = "identical policy boilerplate"

    first = ingest._chunk_id("schemes/a.md", 0, content)

    assert first == ingest._chunk_id("schemes/a.md", 0, content)
    assert first != ingest._chunk_id("schemes/b.md", 0, content)
    assert first != ingest._chunk_id("schemes/a.md", 1, content)


def test_corpus_generation_changes_with_model_or_rows():
    rows = _rows()

    generation = ingest._corpus_generation(rows, "model-a")

    assert generation == ingest._corpus_generation(rows, "model-a")
    assert generation != ingest._corpus_generation(rows, "model-b")
    assert generation != ingest._corpus_generation(
        [{**rows[0], "content": "updated policy"}], "model-a"
    )


def test_replace_corpus_writes_nothing_when_embedding_fails(monkeypatch):
    _embeddings, ensure_table, engine = _install_engine(
        monkeypatch, _RecordingConnection(), fail_embeddings=True
    )

    with pytest.raises(RuntimeError, match="model unavailable"):
        ingest._replace_corpus(_rows())

    ensure_table.assert_not_called()
    assert engine.begin_count == 0


def test_replace_corpus_acquires_lock_before_every_write_and_state(monkeypatch):
    connection = _RecordingConnection()
    _embeddings, ensure_table, engine = _install_engine(monkeypatch, connection)

    count = ingest._replace_corpus(_rows())

    assert count == 1
    assert engine.begin_count == 1
    # Lock is the first statement of the single activation transaction.
    assert "pg_advisory_xact_lock" in connection.statements[0][0]
    assert connection.statements[0][1] is True
    # Every statement (lock, upsert, stale delete, state marker, FTS DDL) runs
    # inside that one transaction.
    assert all(active for _sql, active in connection.statements)
    sqls = [sql for sql, _active in connection.statements]

    def index_of(token):
        return next(i for i, sql in enumerate(sqls) if token in sql)

    lock_index = index_of("pg_advisory_xact_lock")
    insert_index = index_of("INSERT INTO scheme_docs_v2")
    delete_index = index_of("IS DISTINCT FROM")
    state_index = index_of("scheme_docs_vector_metadata")
    fts_index = index_of("tsv tsvector")

    assert lock_index == 0
    assert lock_index < insert_index < delete_index < state_index < fts_index


def test_replace_corpus_lock_failure_aborts_before_any_write(monkeypatch):
    connection = _RecordingConnection(fail_on=("pg_advisory_xact_lock",))
    _embeddings, _ensure_table, engine = _install_engine(monkeypatch, connection)

    with pytest.raises(RuntimeError, match="boom:pg_advisory_xact_lock"):
        ingest._replace_corpus(_rows())

    assert len(connection.statements) == 1
    assert "pg_advisory_xact_lock" in connection.statements[0][0]
    assert engine.last_begin is not None
    assert engine.last_begin.exc_type is RuntimeError
    assert connection.active is False


def test_replace_corpus_write_failure_leaves_no_partial_activation(monkeypatch):
    connection = _RecordingConnection(fail_on=("INSERT INTO scheme_docs_v2",))
    _embeddings, _ensure_table, engine = _install_engine(monkeypatch, connection)

    with pytest.raises(RuntimeError, match="boom:INSERT INTO scheme_docs_v2"):
        ingest._replace_corpus(_rows())

    sqls = [sql for sql, _active in connection.statements]
    assert any("pg_advisory_xact_lock" in sql for sql in sqls)
    assert any("INSERT INTO scheme_docs_v2" in sql for sql in sqls)
    # Nothing after the failed upsert executes: no stale delete, no state
    # marker, no FTS DDL, so the previous generation stays active.
    assert not any("IS DISTINCT FROM" in sql for sql in sqls)
    assert not any("scheme_docs_vector_metadata" in sql for sql in sqls)
    assert not any("tsv tsvector" in sql for sql in sqls)
    assert engine.last_begin is not None
    assert engine.last_begin.exc_type is RuntimeError


def test_replace_corpus_records_state_on_the_locked_connection(monkeypatch):
    rows = _rows()
    connection = _RecordingConnection()
    _embeddings, ensure_table, engine = _install_engine(monkeypatch, connection)

    count = ingest._replace_corpus(rows)

    assert count == 1
    ensure_table.assert_called_once_with(2)
    state_sql = [
        sql for sql, _active in connection.statements
        if "scheme_docs_vector_metadata" in sql
    ]
    assert state_sql
    assert any("INSERT INTO scheme_docs_vector_metadata" in sql for sql in state_sql)
