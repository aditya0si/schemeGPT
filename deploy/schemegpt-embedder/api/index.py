"""SchemeGPT embedder as a Vercel Python function (FastAPI).

Why this exists: the Render free instance (512 MiB) cannot hold the model. Measured
in a real 512 MiB cgroup: the tokenizer alone costs ~300 MB and the int8 ONNX
session ~200 MB, against a 536.9 MB limit with ~98 MB of app — so every live query
was OOM-killed. Vercel Hobby functions get 1024 MB, which fits the same model with
room to spare, and the weights are a public Hugging Face download (no token, no card).

Contract: POST /embed {"inputs": ["query: ...", ...]} -> [[...384 floats...]],
mean-pooled over the attention mask and L2-normalized — the same recipe the corpus
was built with. app/embeddings.py::RemoteEmbeddings sends the E5 prefixes and
refuses any other width, so a wrong answer here cannot silently put queries in a
different vector space.

Routes are declared twice on purpose: Vercel may mount the app under /api/index,
so each endpoint also answers under a prefix (see the `_prefixed` handlers).
"""

import json
import os
import pathlib
import urllib.request

import numpy as np
from fastapi import FastAPI, HTTPException, Request

MODEL = "intfloat/multilingual-e5-small"
BASE = f"https://huggingface.co/{MODEL}/resolve/main"
CACHE = pathlib.Path("/tmp/schemegpt-embedder")
GRAPH = CACHE / "model_qint8_avx512_vnni.onnx"
TOKENIZER = CACHE / "tokenizer.json"
WIDTH = 384
MAX_INPUTS = 64
# Optional shared secret: set EMBED_TOKEN here and EMBEDDING_API_KEY on the caller
# so this is not a free embedding service for the whole internet.
EXPECTED_TOKEN = os.environ.get("EMBED_TOKEN", "")

app = FastAPI(title="SchemeGPT embedder")
_STATE: dict = {}


def _download(url: str, dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=180) as response, open(partial, "wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    partial.replace(dest)


def _load() -> dict:
    """Download once per instance, then load tokenizer and ONNX session."""
    if _STATE:
        return _STATE
    if not GRAPH.exists():
        _download(f"{BASE}/onnx/model_qint8_avx512_vnni.onnx", GRAPH)
    if not TOKENIZER.exists():
        _download(f"{BASE}/tokenizer.json", TOKENIZER)

    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    tokenizer.enable_truncation(max_length=512)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(GRAPH), options, providers=["CPUExecutionProvider"])
    _STATE.update(tokenizer=tokenizer, session=session)
    return _STATE


def _embed(texts: list[str]) -> list[list[float]]:
    state = _load()
    tokenizer, session = state["tokenizer"], state["session"]
    encodings = [tokenizer.encode(text) for text in texts]
    width = max(len(encoding.ids) for encoding in encodings)
    ids = np.zeros((len(encodings), width), dtype=np.int64)
    mask = np.zeros((len(encodings), width), dtype=np.int64)
    for row, encoding in enumerate(encodings):
        ids[row, : len(encoding.ids)] = encoding.ids
        mask[row, : len(encoding.attention_mask)] = encoding.attention_mask
    token_vectors = session.run(
        None,
        {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)},
    )[0]
    pooled = (token_vectors * mask[:, :, None]).sum(axis=1) / mask.sum(axis=1, keepdims=True)
    normalized = pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
    return [[float(value) for value in row] for row in normalized]


def _health() -> dict:
    return {"status": "alive", "model": MODEL, "width": WIDTH, "loaded": bool(_STATE)}


async def _embed_request(request: Request) -> list[list[float]]:
    if EXPECTED_TOKEN and request.headers.get("authorization", "") != f"Bearer {EXPECTED_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON") from None
    inputs = body.get("inputs") if isinstance(body, dict) else body
    if isinstance(inputs, str):
        inputs = [inputs]
    if not isinstance(inputs, list) or not inputs or not all(isinstance(t, str) for t in inputs):
        raise HTTPException(status_code=422, detail="expected {'inputs': [str, ...]}")
    if len(inputs) > MAX_INPUTS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_INPUTS} inputs per request")
    vectors = _embed(inputs)
    if any(len(vector) != WIDTH for vector in vectors):
        raise HTTPException(status_code=500, detail="internal width mismatch")
    return vectors


@app.get("/health")
def health():
    return _health()


@app.post("/embed")
async def embed_endpoint(request: Request):
    return await _embed_request(request)


# Path-agnostic fallback: Vercel mounts the app at its own path (/api/index), so a
# rewritten request can arrive at a path no explicit route matches. Choose the
# operation by method instead, and report the path actually seen.
@app.api_route("/{rest:path}", methods=["GET", "POST"])
async def any_path(request: Request, rest: str):
    if request.method == "GET":
        return {**_health(), "path_seen": request.url.path}
    return await _embed_request(request)
