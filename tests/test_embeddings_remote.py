"""The remote embedding backend: payload shape, prefix handling, fail-closed rules.

The deployed free-tier API cannot hold the model, so it asks a hosted endpoint for
query vectors. These tests pin the properties that keep that safe: the endpoint is
sent the same E5-prefixed text the corpus was built with, the response is parsed as
sentence-level vectors, and anything that would put queries in a different vector
space (token-level output, wrong width, wrong count) is refused instead of used.
"""

import io
import json

import pytest

from app.embeddings import E5PrefixEmbeddings, RemoteEmbeddings, build_embeddings

WIDTH = 384


def _response(vectors):
    """A urlopen-compatible response object returning ``vectors`` as JSON."""
    payload = json.dumps(vectors).encode()

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Response(payload)


@pytest.fixture()
def captured(monkeypatch):
    """Capture every request the backend makes, answering with plausible vectors."""
    seen: list[dict] = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data)
        seen.append({"url": request.full_url, "headers": dict(request.headers), "body": body})
        return _response([[0.01 * (i + 1)] * WIDTH for i in range(len(body["inputs"]))])

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_sends_the_same_e5_prefix_the_corpus_used(captured):
    embeddings = RemoteEmbeddings("intfloat/multilingual-e5-small", api_url="https://example.invalid/embed")
    embeddings.embed_query("how much does PM-KISAN pay?")
    assert captured[-1]["body"]["inputs"] == ["how much does PM-KISAN pay?"]

    prefixed = E5PrefixEmbeddings(embeddings)
    prefixed.embed_query("how much does PM-KISAN pay?")
    assert captured[-1]["body"]["inputs"] == ["query: how much does PM-KISAN pay?"]
    prefixed.embed_documents(["PM-KISAN pays 6000 per year."])
    assert captured[-1]["body"]["inputs"] == ["passage: PM-KISAN pays 6000 per year."]


def test_asks_the_endpoint_to_wait_for_a_cold_model(captured):
    RemoteEmbeddings(api_url="https://example.invalid/embed").embed_query("hello")
    assert captured[-1]["body"]["options"] == {"wait_for_model": True}


def test_sends_the_bearer_token_only_when_configured(captured):
    RemoteEmbeddings(api_url="https://example.invalid/embed").embed_query("hello")
    assert "Authorization" not in captured[-1]["headers"]

    RemoteEmbeddings(api_url="https://example.invalid/embed", api_key="hf_secret").embed_query("hello")
    assert captured[-1]["headers"].get("Authorization") == "Bearer hf_secret"


def test_batches_documents(captured):
    embeddings = RemoteEmbeddings(api_url="https://example.invalid/embed", batch_size=2)
    vectors = embeddings.embed_documents(["a", "b", "c", "d", "e"])
    assert len(vectors) == 5
    assert [len(call["body"]["inputs"]) for call in captured] == [2, 2, 1]


def test_parses_vectors_as_floats(captured):
    vector = RemoteEmbeddings(api_url="https://example.invalid/embed").embed_query("hello")
    assert len(vector) == WIDTH
    assert all(isinstance(value, float) for value in vector)


def test_refuses_token_level_output(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _response([[[0.1, 0.2], [0.3, 0.4]]]),
    )
    with pytest.raises(ValueError, match="token-level"):
        RemoteEmbeddings(api_url="https://example.invalid/embed").embed_query("hello")


def test_refuses_a_width_that_is_not_the_models(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _response([[0.1] * 768]),
    )
    with pytest.raises(ValueError, match="384-dimensional"):
        RemoteEmbeddings(api_url="https://example.invalid/embed").embed_query("hello")


def test_refuses_a_mismatched_vector_count(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _response([[0.1] * WIDTH]),
    )
    with pytest.raises(ValueError, match="1 vectors for 2 inputs"):
        RemoteEmbeddings(api_url="https://example.invalid/embed").embed_documents(["a", "b"])


def test_refuses_to_construct_without_a_url():
    with pytest.raises(ValueError, match="EMBEDDING_API_URL"):
        RemoteEmbeddings(api_url="")


def test_build_embeddings_selects_remote_and_keeps_the_prefix_wrapper(monkeypatch):
    import app.config as config

    monkeypatch.setattr(config.settings, "embedding_api_url", "https://example.invalid/embed")
    monkeypatch.setattr(config.settings, "embedding_api_key", "")

    embeddings = build_embeddings("intfloat/multilingual-e5-small", "remote")
    assert isinstance(embeddings, E5PrefixEmbeddings)
    assert isinstance(embeddings.inner, RemoteEmbeddings)
