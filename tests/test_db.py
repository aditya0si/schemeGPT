"""Database adapter compatibility tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import db


def test_database_url_uses_psycopg3_driver():
    assert db._database_url_for_psycopg(
        "postgresql+psycopg2://scheme:scheme@localhost:5432/schemegpt"
    ) == "postgresql+psycopg://scheme:scheme@localhost:5432/schemegpt"
    assert db._database_url_for_psycopg(
        "postgresql://scheme:scheme@localhost:5432/schemegpt"
    ) == "postgresql+psycopg://scheme:scheme@localhost:5432/schemegpt"


def test_vectorstore_uses_non_deprecated_table_adapter():
    db.get_vectorstore.cache_clear()
    pg_engine = MagicMock()
    with (
        patch.object(db, "_vector_table_exists", return_value=False),
        patch.object(db, "_embedding_dimension", return_value=384),
        patch.object(db, "get_pg_engine", return_value=pg_engine),
        patch.object(db, "get_embeddings", return_value="EMBEDDINGS"),
        patch.object(db.PGVectorStore, "create_sync", return_value="STORE") as create,
    ):
        store = db.get_vectorstore()

    pg_engine.init_vectorstore_table.assert_called_once_with(
        table_name=db.VECTOR_TABLE,
        vector_size=384,
        id_column=db.Column(db.VECTOR_ID_COLUMN, "VARCHAR", nullable=False),
        metadata_json_column=db.VECTOR_METADATA_COLUMN,
        metadata_columns=[
            db.Column(db.VECTOR_GENERATION_COLUMN, "VARCHAR", nullable=False)
        ],
        overwrite_existing=False,
    )
    create.assert_called_once_with(
        engine=pg_engine,
        embedding_service="EMBEDDINGS",
        table_name=db.VECTOR_TABLE,
        id_column=db.VECTOR_ID_COLUMN,
        metadata_json_column=db.VECTOR_METADATA_COLUMN,
        metadata_columns=[db.VECTOR_GENERATION_COLUMN],
    )
    assert store == "STORE"
    db.get_vectorstore.cache_clear()


# --- strict vs lenient corpus-generation reads ------------------------------


class _BoomEngine:
    def connect(self):
        raise RuntimeError("db down")


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *args):
        return False


class _CaptureConn:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements: list[str] = []
        self.params: list = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        self.params.append(params)
        return SimpleNamespace(fetchall=lambda: self.rows)


class _CaptureEngine:
    def __init__(self, rows=None):
        self.conn = _CaptureConn(rows)

    def connect(self):
        return _Ctx(self.conn)


def test_stored_generation_is_lenient_but_strict_reader_raises(monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: _BoomEngine())

    # Best-effort callers still see "unknown" instead of an exception...
    assert db.stored_corpus_generation() is None
    # ...but generation-binding callers must not mistake a DB failure for an
    # uninitialized corpus.
    with pytest.raises(db.CorpusMetadataError):
        db.read_corpus_generation()


def test_fetch_generation_documents_filters_by_generation(monkeypatch):
    engine = _CaptureEngine()
    monkeypatch.setattr(db, "get_engine", lambda: engine)

    db.fetch_generation_documents("gen-a", source="pm-kisan.md")

    statement = engine.conn.statements[0]
    params = engine.conn.params[0]
    assert db.VECTOR_GENERATION_COLUMN in statement
    assert params["generation"] == "gen-a"
    assert params["source"] == "pm-kisan.md"
    assert params["source_suffix"] == "%/pm-kisan.md"


def test_fetch_generation_documents_requires_generation():
    with pytest.raises(ValueError, match="corpus generation"):
        db.fetch_generation_documents("")


def test_fetch_generation_jurisdictions_filters_by_generation(monkeypatch):
    engine = _CaptureEngine(rows=[("Bihar",), ("Kerala",)])
    monkeypatch.setattr(db, "get_engine", lambda: engine)

    names = db.fetch_generation_jurisdictions("gen-b")

    statement = engine.conn.statements[0]
    assert db.VECTOR_GENERATION_COLUMN in statement
    assert engine.conn.params[0]["generation"] == "gen-b"
    assert names == ["Bihar", "Kerala"]


def test_fetch_generation_jurisdictions_requires_generation():
    with pytest.raises(ValueError, match="corpus generation"):
        db.fetch_generation_jurisdictions("")
