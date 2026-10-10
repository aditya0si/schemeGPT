"""Embeddings for SchemeGPT: multilingual E5 model with query/passage prefixes.

The corpus serves an audience that asks in English, Hindi, and Hinglish, so the
embedding model is ``intfloat/multilingual-e5-small`` (384-dim, same pgvector
column width as the previous ``all-MiniLM-L6-v2`` — only the vector space
changes). E5 models are trained with task prefixes: queries must be embedded
with ``"query: "`` and documents with ``"passage: "``. ``E5PrefixEmbeddings``
applies the prefixes transparently so callers (PGVectorStore, evaluation, the hybrid
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


# Models this project registered with fastembed at runtime (fastembed's own
# registry is process-global, so re-registering would append duplicates).
_FASTEMBED_REGISTERED: set[str] = set()
# Embedding width per model family that fastembed does not ship itself.
_FASTEMBED_CUSTOM_DIMS = {"multilingual-e5-small": 384}


def _register_fastembed_model(model_name: str) -> None:
    """Teach fastembed a model whose weights it can fetch but not configure.

    fastembed 0.9 ships ``intfloat/multilingual-e5-large`` but not the small
    variant this project uses. The recipe is read from the model repository
    rather than guessed: ``1_Pooling/config.json`` declares
    ``pooling_mode_mean_tokens: true`` and ``modules.json`` lists a Normalize
    step, which is what ``PoolingType.MEAN`` + ``normalization=True``
    reproduce. Vectors therefore stay in the same space as the
    sentence-transformers path.
    """
    if model_name in _FASTEMBED_REGISTERED:
        return

    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if model_name not in {entry["model"] for entry in TextEmbedding.list_supported_models()}:
        dim = next(
            (value for key, value in _FASTEMBED_CUSTOM_DIMS.items() if key in model_name),
            None,
        )
        if dim is None:
            raise ValueError(
                f"{model_name} is not a fastembed model and its width is unknown; "
                "add it to _FASTEMBED_CUSTOM_DIMS with the width from the model card."
            )
        TextEmbedding.add_custom_model(
            model=model_name,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=model_name),
            dim=dim,
            model_file="onnx/model.onnx",
        )

    _FASTEMBED_REGISTERED.add(model_name)


class FastEmbedEmbeddings(Embeddings):
    """The same E5 model through ONNX Runtime, with no PyTorch dependency.

    The fp32 ``sentence-transformers`` stack plus the 470 MB checkpoint needs
    ~1-2 GB of resident memory; ONNX Runtime streams the same weights into a
    small process instead, which is what lets the API run on a 512 MB free
    instance. Imported lazily so a deployment that selects this backend never
    pays for torch at import time.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _loaded(self):
        if self._model is None:
            from fastembed import TextEmbedding

            _register_fastembed_model(self.model_name)
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(value) for value in vector]
            for vector in self._loaded().embed(list(texts))
        ]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embeddings(model_name: str, backend: str = "sentence_transformers") -> Embeddings:
    """Construct the configured backend, E5-prefixed when the model needs it.

    ``backend="fastembed"`` avoids importing ``langchain_huggingface`` at all,
    so the ONNX deployment never drags PyTorch into the image or the process.
    """
    inner: Embeddings
    if backend == "fastembed":
        inner = FastEmbedEmbeddings(model_name)
    else:
        from langchain_huggingface import HuggingFaceEmbeddings

        inner = HuggingFaceEmbeddings(model_name=model_name)
    if needs_e5_prefixes(model_name):
        return E5PrefixEmbeddings(inner)
    return inner
