"""Embeddings for SchemeGPT: multilingual E5 model with query/passage prefixes.

The corpus serves an audience that asks in English, Hindi, and Hinglish, so the
embedding model is ``intfloat/multilingual-e5-small`` (384-dim, same pgvector
column width as the previous ``all-MiniLM-L6-v2`` — only the vector space
changes). E5 models are trained with task prefixes: queries must be embedded
with ``"query: "`` and documents with ``"passage: "``. ``E5PrefixEmbeddings``
applies the prefixes transparently so callers (PGVector, RAGAS, the hybrid
retriever) never need to know about the convention.
"""

from langchain_core.embeddings import Embeddings

# The default multilingual embedding model (see app.config.Settings).
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"


def needs_e5_prefixes(model_name: str) -> bool:
    """True when a model follows the E5 query/passage prefix convention."""
    return "e5" in str(model_name).lower()


class E5PrefixEmbeddings(Embeddings):
    """Wrap any Embeddings so queries/documents get E5 task prefixes."""

    def __init__(self, inner: Embeddings) -> None:
        self.inner = inner

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(f"query: {text}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(
            [f"passage: {text}" for text in texts]
        )
