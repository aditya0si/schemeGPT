# SchemeGPT embedder (Vercel function)

The query embedder for the deployed API, because the Render free instance cannot
hold the model in-process.

## Why this exists (measured, not estimated)

In a real 512 MiB cgroup (limit 536.9 MB) with the deployed image:

| Component | Peak |
|---|---|
| app baseline (Render instance, model unloaded) | ~98 MB |
| `tokenizers` module imported | 47.5 MB |
| **+ loading `tokenizer.json`** | **+298 MB** (the 250k-vocab unigram trie) |
| + int8 ONNX session (118 MB file) | +199 MB |
| + fp32 ONNX session, for reference | +740 MB |
| fastembed's `TextEmbedding` end to end | 519.5 MB |
| lean ONNX session + SentencePiece instead | 563.6 MB / 350.5 MB |

So the model cannot fit beside the app at 512 MiB whichever graph or tokenizer is
used — the first live query was OOM-killed (`server_failed`, `oomKilled 512Mi`), and
no in-process arrangement changed that. Vercel Hobby functions get **1024 MB**, which
fits the same model with room to spare, and the weights are a public Hugging Face
download — no token, no card, no new account.

## Contract

```
GET  /health -> {"status": "alive", "model": ..., "width": 384, "loaded": bool}
POST /embed  {"inputs": ["query: ...", "passage: ..."]} -> [[384 floats], ...]
```

Vectors are mean-pooled over the attention mask and L2-normalized — the same recipe
the corpus was built with. `app/embeddings.py::RemoteEmbeddings` applies the E5
prefixes and refuses any response whose width is not 384, so a wrong answer here
cannot silently put queries in a different vector space.

Routes are path-agnostic on purpose: Vercel mounts the app at `/api/index` and
rewrites arrive as that path (`path_seen` in the health payload reports it), so the
operation is chosen by HTTP method instead of by path.

The model is downloaded into `/tmp` on the first request of a cold instance
(~135 MB) and cached there for that instance's lifetime: cold ~3.4 s, warm ~0.6 s.

## Deploy

```bash
cd deploy/schemegpt-embedder
vercel deploy --prod --yes --scope <team>
```

`vercel.json` sets `memory: 1024` and `maxDuration: 60` for `api/index.py`.
Deployment Protection must be off for the endpoint to be reachable
(`ssoProtection: null` on the project), and the project's production alias is what
the API is configured against (`EMBEDDING_API_URL`).

## Wiring

Render service `schemegpt-api`:

```
EMBEDDING_BACKEND=remote
EMBEDDING_API_URL=https://schemegpt-embedder.vercel.app/embed
EMBEDDING_MODEL=intfloat/multilingual-e5-small   (unchanged)
```

Optionally set `EMBED_TOKEN` here and `EMBEDDING_API_KEY` there to keep the endpoint
from being a free embedding service for anyone.

## Verification

Retrieval gate through this backend against the hosted corpus, two separate
processes: **hit@4 0.875 / mrr@4 0.802083** — identical to the published numbers,
so the swap does not move the evidence. Fidelity against the fp32 rows already in
the database: mean cosine **0.991** over real corpus chunks (the int8 drift, which
the gate tolerates; the fp32 graph is not needed).
