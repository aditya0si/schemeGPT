"""Multilingual embedding model + E5 prefix wrapper and provenance helpers."""

from app.config import Settings
from app.embeddings import (
    EMBEDDING_MODEL_NAME,
    E5PrefixEmbeddings,
    needs_e5_prefixes,
)


class _FakeInner:
    """Captures what the wrapped embeddings were asked to embed."""

    def __init__(self):
        self.queries: list[str] = []
        self.doc_batches: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.5, 0.5]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.doc_batches.append(texts)
        return [[0.5, 0.5] for _ in texts]


def test_default_embedding_model_is_multilingual():
    # Instantiate without the .env so the default is what we assert.
    fresh = Settings(_env_file=None)
    assert fresh.embedding_model == EMBEDDING_MODEL_NAME
    assert needs_e5_prefixes(EMBEDDING_MODEL_NAME)


def test_needs_e5_prefixes_only_for_e5_models():
    assert needs_e5_prefixes("intfloat/multilingual-e5-small")
    assert needs_e5_prefixes("Multilingual-E5-Large")
    assert not needs_e5_prefixes("all-MiniLM-L6-v2")
    assert not needs_e5_prefixes("bge-m3")


def test_e5_wrapper_prefixes_query():
    inner = _FakeInner()
    wrapped = E5PrefixEmbeddings(inner)
    assert wrapped.embed_query("kisan ko kitna paisa") == [0.5, 0.5]
    assert inner.queries == ["query: kisan ko kitna paisa"]


def test_e5_wrapper_prefixes_documents():
    inner = _FakeInner()
    wrapped = E5PrefixEmbeddings(inner)
    wrapped.embed_documents(["PM-KISAN", "Ayushman Bharat"])
    assert inner.doc_batches == [
        ["passage: PM-KISAN", "passage: Ayushman Bharat"]
    ]
