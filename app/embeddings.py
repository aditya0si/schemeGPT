"""Embeddings for SchemeGPT: multilingual E5 model with query/passage prefixes.

The corpus serves an audience that asks in English, Hindi, and Hinglish, so the
embedding model is ``intfloat/multilingual-e5-small`` (384-dim, same pgvector
column width as the previous ``all-MiniLM-L6-v2`` — only the vector space
changes). E5 models are trained with task prefixes: queries must be embedded
with ``"query: "`` and documents with ``"passage: "``. ``E5PrefixEmbeddings``
applies the prefixes transparently so callers (PGVectorStore, evaluation, the hybrid
retriever) never need to know about the convention.
"""

import os

from langchain_core.embeddings import Embeddings

# The default multilingual embedding model (see app.config.Settings).
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"

# Which ONNX graph fastembed loads for that model. The fp32 export
# (``onnx/model.onnx``) is 470 MB and costs roughly that much resident memory once
# the session maps it — measured as the cause of an OOM kill at 512 MiB on the free
# Render instance, on the first query that needed the model. The int8 export
# (``onnx/model_qint8_avx512_vnni.onnx``) is 118 MB and moved vectors by a mean
# cosine of 0.989 against 60 real corpus chunks. Overridable so a deployment can
# choose the smaller graph without a code change.
EMBEDDING_MODEL_FILE = os.environ.get("EMBEDDING_MODEL_FILE", "onnx/model.onnx")


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
            model_file=EMBEDDING_MODEL_FILE,
        )

    _FASTEMBED_REGISTERED.add(model_name)


class FastEmbedEmbeddings(Embeddings):
    """The same E5 model through ONNX Runtime, with no PyTorch dependency.

    The fp32 ``sentence-transformers`` stack plus the 470 MB checkpoint needs
    ~1-2 GB of resident memory; ONNX Runtime drops the torch dependency and runs
    a much smaller process, which is what makes a free-tier instance viable at
    all. Necessary, not sufficient: the fp32 ONNX graph alone still cost about
    its own file size in resident memory and got a 512 MiB instance OOM-killed
    on the first query that needed it, which is why ``EMBEDDING_MODEL_FILE``
    exists and the deployed image selects the int8 graph. Imported lazily so a
    deployment that selects this backend never pays for torch at import time.
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
    ``backend="remote"`` asks a hosted endpoint (see ``RemoteEmbeddings``) and
    loads no model locally at all.
    """
    inner: Embeddings
    if backend == "remote":
        from app.config import settings

        inner = RemoteEmbeddings(
            model_name,
            api_url=settings.embedding_api_url,
            api_key=settings.embedding_api_key,
        )
    elif backend == "fastembed":
        inner = FastEmbedEmbeddings(model_name)
    else:
        from langchain_huggingface import HuggingFaceEmbeddings

        inner = HuggingFaceEmbeddings(model_name=model_name)
    if needs_e5_prefixes(model_name):
        return E5PrefixEmbeddings(inner)
    return inner


class RemoteEmbeddings(Embeddings):
    """E5 embeddings from a hosted inference endpoint, with no local model.

    Why this exists: the free-tier container cannot hold the model in-process.
    Measured in a real 512 MiB cgroup (limit 536.9 MB) the tokenizer alone costs
    ~300 MB, the int8 ONNX session ~200 MB, and the app's own baseline ~98 MB, so
    the first query is OOM-killed whatever graph is used — fastembed, a lean
    ONNX session and a tuned session all peak at 520-563 MB before the app's
    share. A hosted endpoint that serves the SAME model keeps the corpus and the
    published gate numbers valid; the E5 prefixes are applied by the wrapper
    around this class, exactly as for the local backends.

    Fails closed: an endpoint that answers with token-level output or a vector
    whose width is not the model's would put queries in a different space than
    the stored corpus, so both are refused loudly rather than silently used.
    """

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        api_url: str = "",
        api_key: str = "",
        timeout_s: float = 60.0,
        batch_size: int = 16,
    ) -> None:
        if not api_url:
            raise ValueError(
                "EMBEDDING_API_URL is empty: the remote backend needs a hosted "
                "embedding endpoint. Set it, or choose another EMBEDDING_BACKEND."
            )
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.batch_size = batch_size
        self.dim = _FASTEMBED_CUSTOM_DIMS.get(model_name.rsplit("/", 1)[-1])

    def _post(self, texts: list[str]) -> list[list[float]]:
        import json
        import urllib.request

        body = json.dumps({"inputs": texts, "options": {"wait_for_model": True}}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.api_url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            payload = json.loads(response.read())

        if not isinstance(payload, list) or not payload:
            raise ValueError(f"Embedding endpoint returned {type(payload).__name__}, not a list of vectors.")
        if isinstance(payload[0], list) and payload[0] and isinstance(payload[0][0], list):
            raise ValueError(
                "Embedding endpoint returned token-level output; this backend needs "
                "sentence-level vectors (mean-pooled and normalized) to match the corpus."
            )
        vectors = [[float(value) for value in vector] for vector in payload]
        if len(vectors) != len(texts):
            raise ValueError(
                f"Embedding endpoint returned {len(vectors)} vectors for {len(texts)} inputs."
            )
        if self.dim is not None:
            widths = {len(vector) for vector in vectors}
            if widths != {self.dim}:
                raise ValueError(
                    f"Embedding endpoint returned width(s) {sorted(widths)} but {self.model_name} "
                    f"is {self.dim}-dimensional; the stored corpus would not be comparable."
                )
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._post(texts[start : start + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._post([text])[0]
