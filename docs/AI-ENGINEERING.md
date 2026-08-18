# SchemeGPT — AI Engineering Stack & Methodology

SchemeGPT is a domain-specific RAG (Retrieval-Augmented Generation) system that
answers citizens' questions about Indian government schemes and acts. This
document describes the AI engineering, the techniques behind it, and how to
measure it. It is the technical companion to the README — adapt any section
into it directly.

---

## 1. Architecture

```
browser (Next.js web/:3000)
   │  chat via SSE proxy route (API stays 127.0.0.1:8000-private)
   ▼
FastAPI (app/main.py)  ── social: GROQ_API_KEY (free tier)
   │                     embeddings: local sentence-transformers (offline)
   ▼
pgvector (Postgres 16, db/:5432, NOT published)
   • langchain_pg_embedding   — 384-dim vectors (cmetadata provenance)
   • tsv tsvector + GIN index — full-text channel (hybrid retrieval)
   • profiles table           — saved citizen profiles
eval/                       RAGAS offline harness (dev only, not in image)
scripts/                    data validation, re-embedding, dev stub API
data/                       Markdown corpus (6 verified schemes + 36 state/UT seeds)
```

There are exactly **two** model families, both free:

| Model | Role | When loaded |
| --- | --- | --- |
| `intfloat/multilingual-e5-small` (384-dim) | embeddings — English+Hindi+Hinglish | local, on first embed |
| `BAAI/bge-reranker-base` (optional) | cross-encoder rerank of the fused shortlist | on demand, `ENABLE_RERANKER=1` (~2 GB CPU) |
| Groq `llama-3.3-70b-versatile` | final answers, agentic reasoning | cloud, per query |
| Groq `llama-3.1-8b-instant` | cheap sub-tasks (question normalization) | cloud, per normalization |

No paid embedding API is used anywhere — embeddings and retrieval are fully
local; the only external API is Groq's free tier.

---

## 2. The RAG pipeline

A single request flows through five bounded stages. Every stage is deliberately
honest: when the live path is unavailable, the system returns a clearly-labelled
pre-made demo answer (HTTP 200, never a traceback, never a leaked secret).

1. **Routing** (`app/agent.needs_multi_step`) — a cheap, LLM-free heuristic
   decides single-shot vs. agentic retrieval. Comparative questions
   ("PM-KISAN vs PM-SYM"), questions naming ≥2 schemes, and profile-aware
   personal questions are routed to the tool-calling loop.
2. **Question normalization** (`app.rag.normalize_question`) — broken English,
   Hindi, or Hinglish is rewritten by the *fast* model into one clean retrieval
   query. Any failure falls back to the raw question, so retrieval always
   proceeds. The answer language always matches the question language.
3. **Retrieval** (`app.retrieval.HybridRetriever`) — two channels fused by
   **Reciprocal Rank Fusion**:
   - *Vector*: cosine similarity in the multilingual embedding space.
   - *Full-text*: Postgres `tsvector` with `websearch_to_tsquery` for exact
     keyword hits that embedding fallback can miss.
   - *Optional rerank*: a cross-encoder re-scores the fused shortlist
     (`ENABLE_RERANKER=1`).
4. **Generation** (`app.rag.SYSTEM_PROMPTS`, per-language) — the answer model
   replies in plain, spoken-style language and is instructed to quote the exact
   policy statements it relies on.
5. **Structured quote verification** (`app.quotes`) — see §4.

---

## 3. Streaming (Server-Sent Events)

`POST /query/stream` is the production chat surface (same request schema and
bounds as `POST /query`, which stays stable for API consumers and the eval
harness). Event protocol, in order:

| Event | Payload | Meaning |
| --- | --- | --- |
| `step` | `{tool, summary}` | (agentic path) one tool call executed — audit trail |
| `sources` | `[{source, content, jurisdiction, state, data_status, last_verified, source_url}]` | retrieved roots |
| `token` | `{text}` | one answer fragment, in order |
| `quotes` | `[{text, source, status, verified, matched_source}]` | machine-verified quotes, before `done` |
| `done` | `{mode: live|demo, notice, language}` | terminal success |
| `error` | `{message}` | terminal failure (partial text is kept by the client) |

The browser only ever talks to the `web` service; the Next.js route handler
(`web/app/api/chat/stream/route.ts`) proxies the SSE stream so the API remains
localhost-only in deployment.

---

## 4. Honesty as a system property

The product's integrity is enforced by code, not just by prompt wording:

- **Demo fallback is labelled.** Any live failure path streams a pre-made answer
  flagged `mode: demo` with a clear notice; the UI renders it differently.
- **Provenance on every source.** A `directory_seed` record is never presented
  as a verified eligibility decision (`app/rag.SYSTEM_PROMPTS` honours this;
  `app/ingest._chunk_metadata` stamps it at ingestion).
- **Quotes are machine-verified.** The model emits `> text [source, status]`
  lines; `app/quotes.py` parses them and verifies each against the retrieved
  context — exact normalized containment, or ≥0.85 `difflib` similarity. A
  quote that fails (`verified: false`) is surfaced to the user, never silent
  and never inserted by the system.
- **Bound inputs.** Query text is 2–2000 chars; profile payloads, free-text,
  lists are length- and size-capped (HTTP 422, never logged as content).
- **Protected ingestion.** `POST /ingest` requires `X-Admin-Token`; no token
  configured → 503. Startup auto-ingestion stays idempotent (content-hash ids).

---

## 5. The seven AI-engineering improvements (2026-08-19)

### 5.1 Multilingual embeddings
`app/embeddings.py` swaps `all-MiniLM-L6-v2` for `intfloat/multilingual-e5-small`
(the default, 384-dim, same column width) and applies the E5 convention
(`query:` / `passage:` prefixes) transparently via `E5PrefixEmbeddings`. This
fixes semantically weak Devanagari retrieval, which matters because the audience
asks in Hindi/Hinglish. Changing the model requires re-embedding:
`python scripts/reembed.py --yes` (deletes this collection's vectors, re-ingests,
and records provenance so startup can warn if they ever drift).

### 5.2 Structured quotes with verification
`app/quotes.py` provides pure `parse_quotes` / `verify_quotes`; the stream emits
a `quotes` event before `done`; the UI renders `✓ verified` / `✗ unverified`
rows with the matched source. Exact policy quotes become first-class, auditable
data instead of hopeful prose.

### 5.3 Hybrid retrieval + optional reranking
`app/retrieval.py` implements `rrf_fuse` (Reciprocal Rank Fusion, k=60) over
vector + Postgres full-text, with an optional `BAAI/bge-reranker-base`
cross-encoder stage behind `ENABLE_RERANKER` (kept off for small free-tier VPSes;
loaded lazily, never in tests). The FTS column/index is created idempotently at
startup (`app/db.ensure_fts_index`).

### 5.4 Evaluation as a regression gate
`eval/run_eval.py` now scores **faithfulness, answer_relevancy,
context_precision, context_recall** over a 20-case golden set (incl. Hinglish,
Hindi, comparative, quote-format, out-of-domain). Each run appends to
`eval/results/history.jsonl` with a config fingerprint and the report gains a
"Delta vs previous run" table. `--gate` fails the command unless the aggregate
floors are met:
```
python -m eval.run_eval --gate        # exit 1 if below floors
python -m eval.run_eval --limit 3     # cheap partial run
```
Gate floors: faithfulness ≥ 0.85, answer_relevancy ≥ 0.70
(`eval/run_eval.GATE_FLOORS`). The 0.70 triage threshold for per-case failure is
a diagnostic, not a quality claim.

### 5.5 Agentic multi-step retrieval
`app/agent.py` adds a no-dependency tool-calling loop. A heuristic
(`needs_multi_step`) routes complex questions to an LLM that may call
`search_schemes(query, jurisdiction)`, `get_scheme_details(scheme_id)`, and
`list_jurisdictions()` (max 3 iterations, temperature 0). Tool results are
gathered into de-duplicated context that feeds the same streaming answer chain;
each call is exposed as a `step` event. If the loop gathers nothing, it raises
and the stream degrades to single-shot retrieval before any demo fallback.

### 5.6 Observability
`app/metrics.py` keeps thread-safe in-process counters
(`queries_live`, `queries_demo`, `agent_routes_total`,
`stream_midstream_failures`, …) and a rolling latency window (p50/p95/mean),
exposed at `GET /metrics` as aggregates only — no per-request text, no PII.
Optional LangSmith tracing is env-only: set `LANGSMITH_TRACING=true` and
`LANGSMITH_API_KEY` to get per-chain traces (it ships transitively with
LangChain).

### 5.7 Model routing
`app.rag.get_llm(role, max_tokens)` returns the cheap fast model
(`GROQ_FAST_MODEL`, default `llama-3.1-8b-instant`) for question normalization
and the stronger answer model (`GROQ_MODEL`) for final answers and the agentic
loop. Every generation stays token-bounded.

---

## 6. Configuration reference

Environment variables (`.env.example` documents all of them):

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | (blank → demo) | live answers; also needed for RAGAS eval |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | answer + agent model |
| `GROQ_FAST_MODEL` | `llama-3.1-8b-instant` | normalization / cheap tasks |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | local embeddings (E5-prefixed) |
| `ENABLE_RERANKER` | `0` | `1` loads `bge-reranker-base` (~2 GB) |
| `DATABASE_URL` | `…@db:5432/schemegpt` | pgvector connection |
| `ADMIN_TOKEN` | (blank → ingest disabled) | `POST /ingest` protection |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | unset | optional trace opt-in |

---

## 7. Honest limitations

- **Corpus is not exhaustive.** 6 central schemes are verified samples
  (`sample_verified`) and 36 state/UT entries are `directory_seed` discovery
  records linking to MyScheme. No claim is made that all schemes are ingested;
  scheme-level state eligibility is not individually verified.
- **Demo-mode Hindi keyword matching** normalizes to ASCII, so a pure-Devanagari
  demo request falls back to the generic Hindi record. Live mode is unaffected
  (retrieval is semantic).
- **Fine-tuning is intentionally skipped.** With a 42-record corpus, RAG is the
  right architecture; fine-tuning becomes relevant only as the corpus grows by
  ~100×. Choosing RAG over fine-tuning is itself a documented engineering
  decision, not an omission.
- **The reranker is RAM-bound** and defaults off for small free-tier VPSes.
- **No real account auth** yet (profiles use a one-time save code); real
  password/OAuth auth is future work.
