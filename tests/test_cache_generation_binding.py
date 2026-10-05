"""Regression tests: cache operations must be bound to one corpus generation.

A concurrent corpus rebuild must never let an answer retrieved from generation A
be stored under generation B, and a lookup must not serve an entry once the
active corpus generation has moved on from the generation it was bound to.
These tests reproduce both races deterministically with fakes (no database).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import metrics, semantic_cache


@pytest.fixture(autouse=True)
def _reset_metrics():
    with metrics._lock:
        metrics._counters.clear()
        metrics._token_usage.clear()
        metrics._latencies.clear()
    yield


class _FakeEmbeddings:
    def embed_query(self, _question):
        return [0.0] * 384


class _RecordingConn:
    def __init__(self, rows):
        self.rows = rows
        self.statements: list[str] = []
        self.params: list = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        self.params.append(params)
        return SimpleNamespace(
            first=lambda: self.rows[0] if self.rows else None,
            fetchall=lambda: self.rows,
        )


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *args):
        return False


class _FakeEngine:
    def __init__(self, rows=None):
        self.conn = _RecordingConn(rows or [])

    def begin(self):
        return _Ctx(self.conn)

    def connect(self):
        return _Ctx(self.conn)


def _patch_engine_and_embeddings(monkeypatch, rows=None) -> _FakeEngine:
    engine = _FakeEngine(rows)
    monkeypatch.setattr(semantic_cache, "get_engine", lambda: engine)
    monkeypatch.setattr("app.db.get_embeddings", lambda: _FakeEmbeddings())
    return engine


# --- lookup races a generation change --------------------------------------


def test_lookup_rejects_hit_when_generation_changes_during_lookup(monkeypatch):
    payload = {"answer": "grounded in generation A", "sources": []}
    _patch_engine_and_embeddings(
        monkeypatch, rows=[(json.dumps(payload), 0.99)]
    )
    # Captured/bound generation is A, but the corpus has since moved to B.
    monkeypatch.setattr(semantic_cache, "stored_corpus_generation", lambda: "gen-b")

    assert semantic_cache.lookup("q", "en", "none", "gen-a") is None
    with metrics._lock:
        assert metrics._counters.get("cache_generation_miss", 0) == 1
        assert metrics._counters.get("cache_hit", 0) == 0


def test_lookup_serves_hit_when_bound_generation_still_active(monkeypatch):
    payload = {"answer": "grounded in generation A", "sources": []}
    _patch_engine_and_embeddings(
        monkeypatch, rows=[(json.dumps(payload), 0.99)]
    )
    monkeypatch.setattr(semantic_cache, "stored_corpus_generation", lambda: "gen-a")

    assert semantic_cache.lookup("q", "en", "none", "gen-a") == payload
    with metrics._lock:
        assert metrics._counters.get("cache_hit", 0) == 1
        assert metrics._counters.get("cache_generation_miss", 0) == 0


# --- store races a generation change between retrieval and store -----------


def test_store_skips_when_generation_changed_between_retrieval_and_store(
    monkeypatch,
):
    engine = _patch_engine_and_embeddings(monkeypatch)
    # Retrieval used A; a rebuild committed B before the store ran.
    monkeypatch.setattr(semantic_cache, "stored_corpus_generation", lambda: "gen-b")

    semantic_cache.store("q", "en", "none", {"answer": "from A"}, "gen-a")

    assert not any(
        "INSERT INTO query_cache" in stmt for stmt in engine.conn.statements
    )
    with metrics._lock:
        assert metrics._counters.get("cache_generation_skipped", 0) == 1
        assert metrics._counters.get("cache_error", 0) == 0


def test_store_writes_when_bound_generation_still_active(monkeypatch):
    engine = _patch_engine_and_embeddings(monkeypatch)
    monkeypatch.setattr(semantic_cache, "stored_corpus_generation", lambda: "gen-a")

    semantic_cache.store("q", "en", "none", {"answer": "from A"}, "gen-a")

    assert any(
        "INSERT INTO query_cache" in stmt for stmt in engine.conn.statements
    )
    with metrics._lock:
        assert metrics._counters.get("cache_generation_skipped", 0) == 0


# --- unknown generation fails closed ---------------------------------------


def test_capture_generation_returns_none_only_when_metadata_absent(monkeypatch):
    monkeypatch.setattr(semantic_cache, "read_corpus_generation", lambda: None)
    assert semantic_cache.capture_generation() is None


def test_capture_generation_propagates_db_error(monkeypatch):
    from app.db import CorpusMetadataError

    def boom():
        raise CorpusMetadataError("db down")

    monkeypatch.setattr(semantic_cache, "read_corpus_generation", boom)
    with pytest.raises(CorpusMetadataError):
        semantic_cache.capture_generation()


def test_lookup_disabled_when_generation_unknown(monkeypatch):
    engine = _patch_engine_and_embeddings(monkeypatch)

    assert semantic_cache.lookup("q", "en", "none", None) is None
    # The cache table is never queried under an unknown namespace.
    assert not any("SELECT payload" in stmt for stmt in engine.conn.statements)
    with metrics._lock:
        assert metrics._counters.get("cache_generation_miss", 0) == 1
        assert metrics._counters.get("cache_error", 0) == 0


def test_store_skipped_when_generation_unknown(monkeypatch):
    engine = _patch_engine_and_embeddings(monkeypatch)

    semantic_cache.store("q", "en", "none", {"answer": "x"}, None)

    assert not any(
        "INSERT INTO query_cache" in stmt for stmt in engine.conn.statements
    )
    with metrics._lock:
        assert metrics._counters.get("cache_generation_skipped", 0) == 1
        assert metrics._counters.get("cache_error", 0) == 0


def test_cache_namespace_rejects_unknown_generation(monkeypatch):
    monkeypatch.setattr(semantic_cache, "stored_corpus_generation", lambda: None)
    with pytest.raises(ValueError):
        semantic_cache.cache_namespace()
    with pytest.raises(ValueError):
        semantic_cache.cache_namespace(None)


# --- request paths propagate one captured generation -----------------------


def test_answer_binds_lookup_retrieval_and_store_to_one_generation(monkeypatch):
    import app.rag as rag
    from langchain_core.documents import Document

    source = Document(
        page_content="Policy fact.",
        metadata={"source": "schemes/fact.md", "data_status": "sample_verified"},
    )
    chain = MagicMock()
    chain.invoke.return_value = "> Policy fact. [schemes/fact.md, sample_verified]"

    monkeypatch.setattr(rag.settings, "groq_api_key", "configured")
    monkeypatch.setattr(
        rag.semantic_cache, "capture_generation", lambda: "gen-a"
    )
    lookup = MagicMock(return_value=None)
    store = MagicMock()
    monkeypatch.setattr(rag.semantic_cache, "lookup", lookup)
    monkeypatch.setattr(rag.semantic_cache, "store", store)
    retrieve = MagicMock(return_value=([source], []))
    monkeypatch.setattr(rag, "retrieve_context", retrieve)
    monkeypatch.setattr(rag, "build_answer_chain", lambda language: chain)

    rag.answer("Who receives a pension?")

    lookup.assert_called_once_with("Who receives a pension?", "en", "none", "gen-a")
    retrieve.assert_called_once_with("Who receives a pension?", "en", None, "gen-a")
    store.assert_called_once()
    assert store.call_args.args[4] == "gen-a"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_answer_falls_back_to_demo_when_generation_unknown(monkeypatch):
    import app.rag as rag

    monkeypatch.setattr(rag.settings, "groq_api_key", "configured")
    monkeypatch.setattr(rag.semantic_cache, "capture_generation", lambda: None)
    lookup = MagicMock()
    retrieve = MagicMock()
    monkeypatch.setattr(rag.semantic_cache, "lookup", lookup)
    monkeypatch.setattr(rag, "retrieve_context", retrieve)

    payload = rag.answer("Who receives a pension?")

    assert payload["mode"] == "demo"
    lookup.assert_not_called()
    retrieve.assert_not_called()


def test_answer_falls_back_to_demo_when_generation_read_fails(monkeypatch):
    import app.rag as rag
    from app.db import CorpusMetadataError

    monkeypatch.setattr(rag.settings, "groq_api_key", "configured")

    def boom():
        raise CorpusMetadataError("db down")

    monkeypatch.setattr(rag.semantic_cache, "capture_generation", boom)
    retrieve = MagicMock()
    monkeypatch.setattr(rag, "retrieve_context", retrieve)

    payload = rag.answer("Who receives a pension?")

    assert payload["mode"] == "demo"
    retrieve.assert_not_called()


@pytest.mark.anyio
async def test_stream_binds_cache_and_retrieval_to_one_generation(monkeypatch):
    import app.stream as stream
    from langchain_core.documents import Document

    source = Document(
        page_content="Policy fact.",
        metadata={"source": "schemes/fact.md", "data_status": "sample_verified"},
    )

    class Chain:
        async def astream(self, payload, config):
            yield "> Policy fact. [schemes/fact.md, sample_verified]"

    monkeypatch.setattr(stream.settings, "groq_api_key", "configured")
    monkeypatch.setattr(
        stream.semantic_cache, "capture_generation", lambda: "gen-a"
    )
    lookup = MagicMock(return_value=None)
    store = MagicMock()
    monkeypatch.setattr(stream.semantic_cache, "lookup", lookup)
    monkeypatch.setattr(stream.semantic_cache, "store", store)
    retrieve = MagicMock(return_value=([source], []))
    monkeypatch.setattr(stream, "retrieve_context", retrieve)
    monkeypatch.setattr(stream, "get_llm", lambda: object())
    monkeypatch.setattr(stream, "build_answer_chain", lambda language: Chain())

    raw = "".join([part async for part in stream.stream_answer("question")])
    assert "done" in raw

    lookup.assert_called_once_with("question", "en", "none", "gen-a")
    assert retrieve.call_args.args == ("question", "en", None, "gen-a")
    store.assert_called_once()
    assert store.call_args.args[4] == "gen-a"


@pytest.mark.anyio
async def test_stream_falls_back_to_demo_when_generation_unknown(monkeypatch):
    import app.stream as stream

    monkeypatch.setattr(stream.settings, "groq_api_key", "configured")
    monkeypatch.setattr(stream.semantic_cache, "capture_generation", lambda: None)
    retrieve = MagicMock()
    monkeypatch.setattr(stream, "retrieve_context", retrieve)

    raw = "".join([part async for part in stream.stream_answer("question")])

    assert "event: done" in raw
    assert '"mode": "demo"' in raw
    assert retrieve.call_count == 0


@pytest.mark.anyio
async def test_stream_falls_back_to_demo_when_generation_read_fails(monkeypatch):
    import app.stream as stream
    from app.db import CorpusMetadataError

    monkeypatch.setattr(stream.settings, "groq_api_key", "configured")

    def boom():
        raise CorpusMetadataError("db down")

    monkeypatch.setattr(stream.semantic_cache, "capture_generation", boom)
    retrieve = MagicMock()
    monkeypatch.setattr(stream, "retrieve_context", retrieve)

    raw = "".join([part async for part in stream.stream_answer("question")])

    assert '"mode": "demo"' in raw
    assert retrieve.call_count == 0
