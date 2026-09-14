"""DB-free tests for the lexical source-matching retrieval channel."""
from types import SimpleNamespace
from unittest.mock import patch

from app.retrieval import (
    _generation_sources,
    _lexical_search,
    _query_tokens,
    _rank_sources,
)


class _Conn:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, stmt, params):
        self.engine.calls.append((str(stmt), dict(params)))
        result = self.engine.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(fetchall=lambda: result)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


class _Engine:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def connect(self):
        return _Ctx(_Conn(self))


def test_query_tokens_drop_stopwords_and_short_tokens():
    tokens = _query_tokens("What does PM-Kisan ka paisa kab aata hai?")
    assert "kisan" in tokens
    assert "paisa" in tokens
    # English/Hinglish function words and sub-3-char tokens are removed.
    assert "what" not in tokens
    assert "does" not in tokens
    assert "ka" not in tokens
    assert "kab" not in tokens
    assert "aata" not in tokens
    assert "pm" not in tokens
    assert all(len(token) >= 3 for token in tokens)


def test_source_scoring_ranks_exact_scheme_name_first():
    sources = (
        "myscheme/dsrupdf.md",
        "schemes/pm-sym.md",
        "schemes/pm-kisan.md",
        "myscheme/nsa.md",
    )
    assert _rank_sources(["kisan"], sources) == ["schemes/pm-kisan.md"]


def test_source_scoring_prefers_more_matched_tokens():
    sources = ("schemes/india-tax.md", "schemes/startup-india.md")
    ranked = _rank_sources(["startup", "india"], sources)
    assert ranked[0] == "schemes/startup-india.md"


def test_source_scoring_requires_a_meaningful_token():
    # A single 3-char match ("sym") is not enough: pm-sym stays semantic-only.
    assert _rank_sources(["sym"], ("schemes/pm-sym.md",)) == []


def test_lexical_channel_fetches_one_chunk_per_source_with_parameters():
    _generation_sources.cache_clear()
    source_rows = [("schemes/pm-kisan.md",), ("myscheme/xyz.md",)]
    chunk_rows = [
        ("kisan money chapter", {"source": "schemes/pm-kisan.md", "chunk_index": 1}),
        (
            "PM-KISAN provides kisan support",
            {"source": "schemes/pm-kisan.md", "chunk_index": 0},
        ),
    ]
    engine = _Engine([source_rows, chunk_rows])
    with patch("app.retrieval.get_engine", return_value=engine):
        results = _lexical_search("pm kisan paisa", corpus_generation="gen-x")

    assert [doc.metadata["source"] for doc, _score in results] == [
        "schemes/pm-kisan.md"
    ]
    # Only the best-overlap chunk of the canonical source is contributed.
    assert results[0][0].page_content == "PM-KISAN provides kisan support"

    distinct_sql, distinct_params = engine.calls[0]
    assert "DISTINCT" in distinct_sql
    assert distinct_params == {"generation": "gen-x"}
    assert "schemes/pm-kisan.md" not in distinct_sql

    fetch_sql, fetch_params = engine.calls[1]
    assert "schemes/pm-kisan.md" not in fetch_sql
    assert fetch_params["generation"] == "gen-x"
    assert fetch_params["source_0"] == "schemes/pm-kisan.md"


def test_lexical_channel_degrades_to_empty_list_on_error():
    _generation_sources.cache_clear()
    engine = _Engine([RuntimeError("db down")])
    with patch("app.retrieval.get_engine", return_value=engine):
        assert _lexical_search("pm kisan", corpus_generation="gen-y") == []


def test_source_scan_is_cached_once_per_generation():
    _generation_sources.cache_clear()
    engine = _Engine([[("schemes/a.md",)]])
    with patch("app.retrieval.get_engine", return_value=engine):
        _lexical_search("kisan", corpus_generation="gen-z")
        _lexical_search("kisan", corpus_generation="gen-z")

    distinct_calls = [call for call in engine.calls if "DISTINCT" in call[0]]
    assert len(distinct_calls) == 1
