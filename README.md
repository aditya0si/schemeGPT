# SchemeGPT 🇮🇳

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![pgvector](https://img.shields.io/badge/pgvector-PostgreSQL%2016-336791.svg)](https://github.com/pgvector/pgvector)
[![Groq gpt-oss](https://img.shields.io/badge/LLM-Groq%20gpt-oss--120b-orange.svg)](https://groq.com/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Quality Evaluation](https://img.shields.io/badge/Eval-Hit%404%20%2B%20MRR%404-green.svg)](eval/retrieval_gate.py)
[![CI](https://github.com/aditya0si/schemeGPT/actions/workflows/ci.yml/badge.svg)](https://github.com/aditya0si/schemeGPT/actions/workflows/ci.yml)
[![Retrieval quality gate](https://github.com/aditya0si/schemeGPT/actions/workflows/eval.yml/badge.svg)](https://github.com/aditya0si/schemeGPT/actions/workflows/eval.yml)

> **SchemeGPT** is an open-source, domain-specific Retrieval-Augmented Generation (RAG) and decision-support engine for Indian Government Schemes, Central Acts, and State/UT Public Welfare Directories. It combines three-channel hybrid retrieval — pgvector dense embeddings, PostgreSQL `tsvector` full-text search, and a lexical scheme-name channel — fused with Reciprocal Rank Fusion, with the final top-4 kept source-diverse (one chunk per document). It also provides exact quote verification and deterministic citizen profile matching. The platform serves bilingual (English & Hindi) query responses with source-bound quote verification that rejects mismatched citations.

---

![SchemeGPT Demo Placeholder](https://raw.githubusercontent.com/aditya0si/schemeGPT/main/docs/demo.png)
*Figure: Real-time SSE streaming answers with inline quote verification, deterministic profile matching, and bilingual search.*

---

## 📌 Keywords & Technical Domain Tags

`RAG` · `Retrieval-Augmented Generation` · `AI Engineering` · `pgvector` · `Reciprocal Rank Fusion (RRF)` · `FastAPI` · `Next.js 16` · `Streamlit` · `Groq gpt-oss` · `LangChain` · `Sentence-Transformers` · `Indian Government Schemes` · `MyScheme India` · `Public Welfare AI` · `SSE Streaming` · `Quote Verification` · `Deterministic Retrieval Evaluation` · `Multi-Step Tool-Calling Agent` · `Bilingual NLP (English + Hindi)` · `Docker Compose`

---

## 📑 Table of Contents

- [Why SchemeGPT](#why-schemegpt)
- [Quick Numbers](#quick-numbers)
- [Key Features](#key-features)
- [Comparison: Naive RAG vs SchemeGPT](#comparison-naive-rag-vs-schemegpt)
- [Sample Query & Verification Trace](#sample-query--verification-trace)
- [System Architecture & RAG Pipeline](#system-architecture--rag-pipeline)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [API Endpoints Summary](#api-endpoints-summary)
- [Deployment](#deployment)
  - [Docker Compose One-Liner](#docker-compose-one-liner)
  - [Port Mappings](#port-mappings)
  - [Environment Variables](#environment-variables)
  - [Production VPS Runbook](#production-vps-runbook)
- [Local Development](#local-development)
- [Groq API Key & Demo Fallback](#groq-api-key--demo-fallback)
- [Evaluation Suite](#evaluation-suite)
- [Smoke Verification](#smoke-verification)
- [Operational Disclaimers](#operational-disclaimers)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why SchemeGPT

Indian government welfare schemes are fragmented across 30+ central ministry portals and state department websites, creating massive discovery friction for eligible citizens. Overlapping eligibility conditions, dense administrative terminology, and regional language barriers frequently prevent qualifying beneficiaries from claiming entitlements. SchemeGPT solves this by unifying official guidelines into an engineered RAG pipeline that verifies every claim against indexed source text.

---

## Quick Numbers

- **~2,100 scheme records**: 6 hand-verified central schemes, 36 state/UT directory seeds, and 2,052 automated myScheme-portal imports (each labeled with its data_status — the system never blurs verified and imported records).
- **RRF hybrid retrieval**: Reciprocal Rank Fusion fusing dense `multilingual-e5-small` embeddings, PostgreSQL `tsvector` keyword search, and a lexical scheme-name channel into a source-diverse top-4 (one chunk per document).
- **Deterministic retrieval gate**: Required CI measures Hit@4 and MRR@4 across 16 source-labelled cases; live generation judging remains a separate manual experiment.
- **FastAPI + Next.js 16**: Asynchronous FastAPI service streaming Server-Sent Events to an editorial Next.js 16 frontend and Streamlit demo.
- **Bilingual EN/HI**: Native multi-lingual query understanding, cross-language vector retrieval, and localized UI controls.
- **Quote-verified answers**: Deterministic exact substring validation preventing fabricated clauses, amounts, or guidelines.

---

## Key Features

- **Hybrid RRF Search**: Fuses pgvector cosine search, PostgreSQL `tsvector` keyword search, and a lexical scheme-name channel with Reciprocal Rank Fusion, then keeps one chunk per source for a source-diverse top-4.
- **Exact Quote Verification**: Cross-references every generated statement against source Markdown chunks via strict substring matching.
- **Multi-Step Agent Retrieval**: Executes iterative tool-calling sequences for comparative, multi-scheme, and constraint-heavy queries.
- **Deterministic Profile Matching**: Recommends applicable welfare programs based on demographic, income, occupational, and location parameters without ungrounded LLM guessing.
- **SSE Token Streaming**: Streams live answer tokens and intermediate agent search events via Server-Sent Events.
- **Retrieval Quality Gate**: Runs a secret-free production retrieval benchmark in required CI and rejects incomplete or below-floor runs.
- **Dual Client Interfaces**: Provides an editorial Next.js 16 web application alongside an interactive Streamlit demonstration interface.
- **Zero-Key Demo Fallback**: Returns indexed reference answers when external LLM endpoints are unavailable or unconfigured.

---

## Comparison: Naive RAG vs SchemeGPT

| Capability / Metric | Naive RAG Baseline | SchemeGPT Pipeline |
| :--- | :--- | :--- |
| **Retrieval Mechanism** | Single-index dense vector search (misses acronyms and exact scheme identifiers) | Three-channel RRF combining dense `multilingual-e5-small` vectors + PostgreSQL `tsvector` full-text search + a lexical scheme-name channel, returning one chunk per source |
| **Citation & Factuality** | Generative citations prone to hallucinated eligibility limits and benefit sums | Deterministic substring quote verification against indexed scheme documentation |
| **Complex Queries** | Single-turn context dump without multi-document synthesis | Multi-step agent loop with tool-based iterative retrieval and comparison |
| **Evaluation Gate** | Ad-hoc manual spot checking without CI quality regression tracking | Deterministic 16-case Hit@4/MRR@4 retrieval gate, plus manual complete-coverage LLM-judge experiments |
| **Multilingual Handling** | Standard English-only tokenization with degraded cross-lingual recall | Native bilingual vector space alignment and localized query normalization |
| **Streaming & Telemetry** | Monolithic blocking response with no step visibility | Real-time SSE streaming with inline agent execution telemetry and quote verification events |

---

## Sample Query & Verification Trace

### User Query
> *"Am I eligible for PM-KISAN if my family owns 1.5 hectares of cultivable land, and what is the annual financial benefit?"*

### Verified System Response
> **Eligibility Status:** Eligible (subject to standard exclusion criteria).
>
> **Details:** Small and marginal farmer families with combined landholdings up to 2 hectares qualify for PM-KISAN, provided no family member falls under institutional or statutory exclusion categories (e.g., income tax payees or constitutional post holders).
>
> **Financial Benefit:** The scheme provides **₹6,000 per year** per family, disbursed in **three equal four-monthly instalments of ₹2,000 each** via Direct Benefit Transfer (DBT).
>
> **Verified Source Quote:**
> - *"Under the PM-KISAN scheme, all landholding farmer families having cultivable landholding up to 2 hectares are provided financial benefit of Rs.6000/- per annum per family payable in three equal installments of Rs.2000/- each, every four months."* — [PM-KISAN Guidelines](https://pmkisan.gov.in/)

### Agent Execution Trace (JSON)

```json
{
  "query": "Am I eligible for PM-KISAN if my family owns 1.5 hectares of cultivable land, and what is the annual financial benefit?",
  "intent": "eligibility_and_benefits",
  "steps": [
    {
      "step": 1,
      "tool": "hybrid_search",
      "args": { "query": "PM-KISAN land eligibility benefit amount installment", "top_k": 5 },
      "results_count": 3,
      "top_rrf_score": 0.0328
    },
    {
      "step": 2,
      "tool": "verify_quotes",
      "args": { "source_doc": "pm-kisan.md" },
      "claims_extracted": 2,
      "quotes_verified": 2,
      "verification_status": "PASSED"
    }
  ],
  "model": "openai/gpt-oss-120b",
  "latency_ms": 742
}
```

---

## Measured Results

Reproduce these with the commands in `eval/` and `loadtest/`. CI uploads
machine-readable evaluation artifacts for each run; local live-run history is
intentionally git-ignored. Experiment context lives in
[`EXPERIMENTS.md`](EXPERIMENTS.md).

**Serving layer** (Locust, 25 concurrent users, 60 s, demo-mode SSE — full
`sources → token* → done` event sequences required for success): **860/860
streams succeeded, 0 failures, 14.5 streams/s, median 11 ms, p95 25 ms,
p99 51 ms** (`loadtest/RESULTS.md`).

**Retrieval quality:** `.github/workflows/eval.yml` runs a no-secret,
deterministic gate against 16 source-labelled English, Hindi, Hinglish, profile,
and jurisdiction cases. It exercises the production hybrid pgvector + Postgres
full-text + lexical scheme-name retriever and fails on incomplete coverage, retrieval errors,
Hit@4 below 0.85, or MRR@4 below 0.60. Each run uploads
`retrieval_scores.json`; run it locally with `python -m eval.retrieval_gate`
after ingesting the corpus.

**Generation quality (LLM judge):** live LLM judging is a manual experiment because
Groq's free-tier daily quota can make infrastructure failures look like quality
regressions. The previous framework report was incomplete (different metrics
had only 5–18 scores out of 20), so it is not presented as a valid baseline.
`python -m eval.run_eval --gate` now requires every selected row to be completely
scored with zero pipeline/evaluation errors before aggregate floors can pass.
The manual `Live generation quality experiment` workflow uploads the report, scores, and run
history; no generation baseline will be published until a full set completes.

**Cost engineering:** per-model token usage is tracked on `/metrics`
(reference list-price mapping in `app/rag.py`), the semantic cache serves
paraphrased repeats without an LLM call (hit rate on `/metrics`), invalidates
entries when the verifier contract, embedding model, answer model, answer-prompt
version, or corpus generation changes, and re-verifies quote flags on every hit. The per-IP token bucket (`RATE_LIMIT_RPM`, default 20/min) keeps a public
deployment inside the shared free-tier quota.

---

## System Architecture & RAG Pipeline

```mermaid
flowchart TD
    subgraph Clients["User Interfaces"]
        UI_Web["Next.js 16 Web Portal (Port 3000)"]
        UI_Streamlit["Streamlit Chat Demo (Port 8501)"]
    end

    subgraph API["FastAPI Backend (app/)"]
        EP_Query["POST /query & /query/stream"]
        EP_Rec["POST /recommendations"]
        EP_Prof["POST/GET /profiles"]
        EP_Cov["GET /coverage & /states"]
        Agent["Multi-Step Agent / RAG Chain"]
        RRF["Reciprocal Rank Fusion (RRF)"]
    end

    subgraph Engine["LLM & Embeddings"]
        Groq["ChatGroq (gpt-oss-120b / gpt-oss-20b)"]
        ST["Sentence-Transformers (384-dim)"]
    end

    subgraph Storage["PostgreSQL 16 + pgvector"]
        VecStore["pgvector Cosine Search"]
        FTS["Postgres Full-Text Index (tsvector)"]
        Lexical["Lexical Scheme-Name Channel"]
        ProfileDB["Saved Profiles & Token Hashes"]
    end

    UI_Web --> EP_Query & EP_Rec & EP_Prof & EP_Cov
    UI_Streamlit --> EP_Query & EP_Rec & EP_Prof & EP_Cov

    EP_Query --> Agent
    Agent --> ST
    ST --> VecStore
    Agent --> RRF
    RRF --> VecStore & FTS & Lexical
    Agent --> Groq
    Groq --> EP_Query
    EP_Prof --> ProfileDB
```

> **AI Engineering Deep-Dive:** The complete technical specification of the RAG pipeline, streaming protocol, quote verification algorithms, evaluation harness, and design trade-offs are documented in [`docs/AI-ENGINEERING.md`](docs/AI-ENGINEERING.md).

---

## Tech Stack

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12), Uvicorn, Pydantic v2
- **Vector Store & Database**: [PostgreSQL 16](https://www.postgresql.org/) with [pgvector](https://github.com/pgvector/pgvector) and the maintained `langchain-postgres` `PGVectorStore` adapter
- **LLM Engine**: [Groq API](https://console.groq.com/) using `openai/gpt-oss-120b` (synthesis) and `openai/gpt-oss-20b` (routing)
- **Embedding Model**: `intfloat/multilingual-e5-small` (384 dimensions, local PyTorch CPU execution)
- **Frontend Applications**:
  - **Next.js 16**: TypeScript, Tailwind CSS, React 19 (`web/`)
  - **Streamlit**: Python Chat UI (`streamlit_app.py`)
- **Evaluation Suite**: deterministic source-retrieval gate (`eval/retrieval_gate.py`) plus an optional provider-neutral LLM-judge experiment (`eval/run_eval.py`)
- **Containerization**: Docker, Docker Compose

---

## Repository Structure

```
SchemeGPT/
├── app/                      # FastAPI Backend Application
│   ├── main.py               # API endpoints, FastAPI router, CORS & metrics
│   ├── rag.py                # Core RAG pipeline, prompt templates & ChatGroq integration
│   ├── retrieval.py          # Hybrid vector + full-text + lexical scheme-name retrieval (RRF)
│   ├── agent.py              # Multi-step tool-calling comparative retrieval agent
│   ├── recommend.py          # Deterministic scheme recommendation engine
│   ├── profiles.py           # Saved citizen profile storage & security
│   ├── ingest.py             # Idempotent document ingestion & vector chunking
│   ├── stream.py             # Server-Sent Events (SSE) streaming handler
│   ├── quotes.py             # Sub-string quote verification & source mapping
│   ├── db.py                 # Postgres connection pool & pgvector setup
│   └── config.py             # Environment configuration & Pydantic settings
├── data/                     # Ingested Knowledge Base
│   ├── schemes/*.md          # Verified central scheme records (PM-KISAN, PM-JAY, etc.)
│   ├── states/*.md           # 36 State / UT directory seed markdown records
│   ├── scheme_catalog.json   # Catalog metadata & eligibility tags
│   └── india_states.json     # Official state/UT directory mapping
├── web/                      # Next.js 16 Web Portal Application
├── streamlit_app.py          # Interactive Streamlit Demo Chat Application
├── eval/                     # Retrieval and generation evaluation suite
│   ├── run_eval.py           # Evaluation runner with quality thresholds & reporting
│   └── questions.json        # Curated test evaluation dataset (English + Hindi)
├── loadtest/                 # Locust load test for the SSE endpoint (+ RESULTS.md)
├── docs/                     # Documentation & Specifications
│   ├── AI-ENGINEERING.md     # In-depth architectural & RAG design guide
│   ├── DEPLOY.md             # Hosted deployment runbook (Vercel + Fly.io + Neon)
│   └── data-operations.md    # Scheme catalog curation & verification workflow
├── scripts/                  # Helper scripts
│   ├── validate_data.py      # Dependency-free schema & directory validator
│   ├── fetch_myscheme.py     # Corpus expansion: myScheme portal dataset -> Markdown
│   ├── reembed.py            # Rebuild vectors after an embedding-model change
│   └── feedback_to_eval.py   # Curated user feedback -> candidate eval cases
├── .github/workflows/        # CI (tests, data validation, web build) + weekly eval gate
├── fly.toml                  # Fly.io deployment config for the API
├── EXPERIMENTS.md            # Run-by-run experiment log with config fingerprints
├── Dockerfile                # API container multi-stage build
├── docker-compose.yml        # Multi-container orchestration (DB, API, Web, Streamlit)
├── requirements.txt          # Production Python dependencies
└── README.md                 # Primary documentation
```

---

## API Endpoints Summary

| Endpoint | Method | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET /livez` | `GET` | Process liveness probe with no dependency I/O. | None |
| `GET /readyz` | `GET` | Traffic-readiness check for database, complete active corpus generation, and embedding-model compatibility. | None |
| `GET /health` | `GET` | Backwards-compatible database health check. | None |
| `POST /query` | `POST` | Primary hybrid-RAG endpoint returning source-bound verified quotes. | None |
| `POST /query/stream` | `POST` | SSE real-time streaming RAG answer output with step events. | None |
| `GET /states` | `GET` | List all 36 Indian States and Union Territories directory records. | None |
| `GET /coverage` | `GET` | Report total catalog coverage (verified schemes vs directory seeds). | None |
| `POST /recommendations`| `POST` | Generate profile-matched scheme recommendations deterministically. | None |
| `POST /profiles` | `POST` | Create a saved citizen profile and receive an access token. | None |
| `GET /profiles/{id}` | `GET` | Retrieve saved citizen profile by ID. | Header: `X-Profile-Token` |
| `PUT /profiles/{id}` | `PUT` | Update saved citizen profile. | Header: `X-Profile-Token` |
| `DELETE /profiles/{id}`| `DELETE` | Delete saved citizen profile. | Header: `X-Profile-Token` |
| `POST /ingest` | `POST` | Trigger re-ingestion of `data/schemes` & `data/states` vectors. | Header: `X-Admin-Token` |
| `GET /metrics` | `GET` | Observability metrics: request counters, latency percentiles, semantic-cache hit rate, per-model token usage. | None |
| `POST /feedback` | `POST` | Thumbs-up/down rating on one answer; curated ratings grow the eval set (`scripts/feedback_to_eval.py`). | None |

---

## Deployment

### Docker Compose One-Liner

```bash
cp .env.example .env && docker compose up -d --build
```

### Port Mappings

| Service | Container Port | Host Port | Accessibility |
| :--- | :--- | :--- | :--- |
| **Next.js Web Portal** | `3000` | `3000` | Public / Web Browser |
| **Streamlit Demo UI** | `8501` | `8501` | Public / Web Browser |
| **FastAPI Backend** | `8000` | `127.0.0.1:8000` | Localhost / Internal Network |
| **PostgreSQL + pgvector** | `5432` | `5432` (internal) | Isolated Docker Network |

### Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | Optional | `""` (Demo Mode) | Groq API key for `openai/gpt-oss-120b` synthesis (and `gpt-oss-20b` normalization). Blank falls back to demo mode. |
| `DATABASE_URL` | Yes | `postgresql://scheme:scheme@db:5432/schemegpt` | PostgreSQL connection string. |
| `ADMIN_TOKEN` | Optional | `""` (Disabled) | Secret token required for authenticated `POST /ingest`. |
| `STREAMLIT_API_URL` | No | `http://api:8000` | Internal API URL used by the Streamlit frontend container. |
| `API_URL` | No | `http://localhost:8000` | API base URL for the Next.js server-side proxy (`/api/chat/stream`, `/api/chat/feedback`) — the browser only talks to Next.js, so CORS stays closed. |

### Production VPS Runbook

1. **Host Firewall & Port Configuration**:
   ```bash
   sudo ufw allow 22/tcp
   sudo ufw allow 8501/tcp
   sudo ufw allow 3000/tcp
   sudo ufw enable
   ```
   *Note: Port 8000 (API) binds to `127.0.0.1` and Port 5432 (Postgres) remains internal to Docker.*

2. **System Requirements & CPU Optimization**:
   - Minimum: 2 GB RAM / 20 GB Disk. Recommended: 4 GB RAM (e.g. ARM Ampere instance).
   - CPU-only PyTorch build (`torch==2.6.0+cpu`) ensures lightweight memory footprint without GPU overhead.

3. **Database Backup & Restoration**:
   ```bash
   # Export snapshot
   docker compose exec db pg_dump -U scheme -d schemegpt > backup_schemegpt.sql
   # Restore snapshot
   docker compose exec -T db psql -U scheme -d schemegpt < backup_schemegpt.sql
   ```

---

## Local Development

1. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Set GROQ_API_KEY if testing live LLM responses; change db host from 'db' to 'localhost'
   ```
2. **Setup Virtual Environment:**
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate | Unix: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Start Database:**
   ```bash
   docker compose up -d db
   ```
4. **Run API & Web Services:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   # In a separate terminal:
   streamlit run streamlit_app.py
   ```

---

## Groq API Key & Demo Fallback

The only external API dependency is Groq for LLM inference. Get a free key at [console.groq.com](https://console.groq.com).

- **Demo Fallback (No Key Required)**: When `GROQ_API_KEY` is omitted or empty, `/query` returns labeled sample responses (`"mode": "demo"`) for standard schemes (PM-KISAN, PM-JAY, PMAY-G, PM-SYM, Startup India, GST).
- **Live RAG Mode**: Adding a valid key enables real-time vector retrieval, agent tool execution, and dynamic answer synthesis.

---

## Evaluation Suite

Evaluation measures retrieval and generation quality against curated cases in `eval/questions.json`. Required CI uses secret-free Hit@4/MRR@4; the optional generation experiment uses the configured Groq judge model.

| Metric | Target Floor | Description |
| :--- | :--- | :--- |
| **Faithfulness** | `>= 0.85` | Ensures answer claims are directly grounded in retrieved context chunks. |
| **Answer Relevancy** | `>= 0.70` | Measures alignment between the user's question and generated response. |
| **Context Precision** | measured | LLM-judge estimate of how much retrieved context is relevant (no gate floor yet). |
| **Context Recall** | measured | LLM-judge estimate of whether context covers the reference answer (no gate floor yet). |

```bash
# Install production plus evaluation dependencies
pip install -r requirements.txt -r requirements-eval.txt

# Deterministic production-retrieval gate (no LLM key; database required)
python -m eval.retrieval_gate

# Optional live generation experiment (Groq quota applies)
python -m eval.run_eval --limit 5 --gate
```

Evaluation outputs are generated to:
- `eval/results/report.md`: Markdown summary report with aggregate scores and regression triage flags.
- `eval/results/scores.json`: Machine-readable score breakdown per evaluation sample.

---

## Smoke Verification

Run quick validation tests locally or on CI without external API dependencies:

```bash
# 1. Syntax & compilation check
python -m py_compile app/*.py streamlit_app.py scripts/*.py eval/*.py

# 2. Schema and state directory validation
python scripts/validate_data.py

# 3. Docker Compose configuration verification
docker compose config --quiet

# 4. Liveness and dependency readiness checks
curl http://localhost:8000/livez
curl http://localhost:8000/readyz
curl http://localhost:8000/coverage
```

---

## Operational Disclaimers

- **Coverage Transparency**: The knowledge base indexes all 36 state/UT jurisdictions via directory seeds (`directory_seed`) alongside central verified schemes (`sample_verified`). Directory seeds link directly to official portals; always consult official ministry channels for formal applications.
- **Privacy Design**: Saved profiles are identified by one-way SHA-256 token hashes. No government identity numbers (Aadhaar, PAN) should ever be entered into the system.
- **Informational Purpose**: SchemeGPT outputs are decision-support aids and do not constitute statutory legal advice or government guarantee of benefits.

---

## Roadmap

- [ ] Add WhatsApp and Telegram bot interfaces for conversational citizen queries
- [ ] Expand full-text coverage to 500+ state-level welfare scheme operational guidelines
- [ ] Implement OCR document pipeline for automated application form parsing
- [ ] Integrate Bhashini API for voice-driven regional Indian dialect translation
- [ ] Add automated eligibility checklist verification against anonymized user documents

---

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
