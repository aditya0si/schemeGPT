# SchemeGPT

A domain RAG question-answering platform over Indian government schemes and acts.

## Architecture

- **API**: FastAPI + uvicorn (`app/`) with endpoints: `/health`, `/query`,
  `/states`, `/profiles`, `/recommendations`, `/coverage`, plus protected
  `POST /ingest` (requires the `X-Admin-Token` header).
- **Vector store**: pgvector (`pgvector/pgvector:pg16`) storing 384-dim embeddings from `all-MiniLM-L6-v2`.
- **Retrieval chain**: LangChain built-ins `create_retrieval_chain` + `create_stuff_documents_chain`.
- **LLM**: `ChatGroq` with `llama-3.3-70b-versatile` (the only external API call; free tier).
- **Embeddings**: `sentence-transformers`, fully local and free.
- **Demo**: Streamlit chat UI (`streamlit_app.py`).
- **Deployment**: Docker Compose (database, API, web).

## Quickstart (Docker)

1. `cp .env.example .env` (Windows: `copy .env.example .env`).
   - **No key yet? Leave `GROQ_API_KEY` blank.** The API runs in demo fallback
     mode: `/query` returns clearly-labelled pre-made answers, so the UI stays
     usable before you add a key.
   - For live Groq RAG answers, set `GROQ_API_KEY` (free tier at
     https://console.groq.com).
   - **`ADMIN_TOKEN` (optional):** leave blank to disable manual `POST /ingest`
     (it returns 503 "disabled"); set one (e.g. via
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`) to enable
     token-protected re-ingestion. Startup auto-ingestion runs regardless.
2. `docker compose up --build`
3. Open http://localhost:8501 (chat demo) and http://localhost:8000/docs (API docs).

   Note: the API port is bound to **localhost only** (`127.0.0.1:8000`), so the
   docs are reachable on the machine running the stack (or over an SSH tunnel
   on a VPS - see the deployment section). The Streamlit UI and the web
   container's internal calls to the API are unaffected.

The API auto-ingests all `data/schemes/*.md` and `data/states/*.md` files on
first startup if the vector store is empty (unchanged and idempotent), and
exposes `POST /ingest` to re-ingest on demand **behind an admin token**: send
the `X-Admin-Token` header matching `ADMIN_TOKEN`, otherwise the endpoint
returns 401/503 and is never exposed publicly. Ingestion is idempotent
(content-hash chunk ids) and never deletes existing vectors; already-ingested
chunks only get their catalog metadata refreshed. The state directory is picked
up automatically even when `DATA_DIR` still points at the old `data/schemes`
value.

## Iteration 1: nationwide discovery, saved profiles, recommendations

- **`GET /states`** - returns the 36 state/Union Territory directory records
  (28 states + 8 UTs) from `data/india_states.json` in stable order. Every
  record is a `directory_seed`: it links to the official national MyScheme
  discovery portal (`https://www.myscheme.gov.in/`) and makes no scheme-level
  eligibility claims.
- **`data/states/*.md`** - one honest directory entry per state/UT. These are
  discovery/coverage seeds (`data_status: directory_seed`), never verified
  eligibility decisions. They are ingested into the vector store so every
  jurisdiction is searchable through RAG.
- **`POST /recommendations`** - deterministic starter recommendations from
  `data/scheme_catalog.json`. No LLM is called in this iteration: central
  sample schemes are ranked with simple, explainable profile signals (age,
  income, occupation, goals, rural), the matching state/UT directory seed is
  appended when a state is selected, and a clear verification disclaimer is
  always returned.
- **Saved profiles** (`POST/GET/PUT/DELETE /profiles`): citizens can save a
  profile and retrieve/update/delete it later. This is a **low-traffic MVP
  capability**: a profile is protected by an opaque one-time access token
  (returned only on creation, required via the `X-Profile-Token` header for
  read/update/delete, stored only as a SHA-256 hash). There is **no account
  authentication yet** - real account auth (passwords, sessions, OAuth) is a
  later iteration. Do not build product decisions on this capability's security
  model.
- **Optional profile fields:** every profile field is optional and nothing is
  collected implicitly. In the UI, area (rural/urban) and disability are
  voluntary: each has a stable "Not specified / Prefer not to say" option (in
  English and Hindi) that is the default, and the raw value sent to the API is
  `None` (field omitted) unless the citizen explicitly picks Rural/Urban or
  Yes/No. Switching the UI language never changes the stored widget values.
- Future seams: the profile `language` field accepts `en`/`hi` (Hindi UI later),
  and recommendation signals are ready to be replaced by scenario-based RAG.

## Iteration 4: honest coverage, verified-data workflow, protected ingestion

### Coverage transparency — `GET /coverage`

`GET /coverage` returns a pure report over `data/india_states.json` and
`data/scheme_catalog.json`:

- **36 jurisdictions** (28 states + 8 UTs), with their names and counts;
- catalog totals: **42 records** today — **6 central verified/sample records**
  (`data_status: sample_verified`) and **36 directory seeds**
  (`data_status: directory_seed`);
- a clear **`coverage_note`**: state/UT directory seeds are discovery entries,
  **not** exhaustive verified scheme databases, and **no claim is made that all
  government schemes have been ingested**;
- optional per-jurisdiction status/counts.

`/states` is unchanged. The Streamlit hero pill uses `/coverage` when available
("36 jurisdictions mapped · 6 verified sample schemes · state directories
expanding" in English and Hindi) and falls back to the static copy otherwise.

### Verified-data workflow — `docs/` and `scripts/validate_data.py`

- **`docs/data-operations.md`** — the repeatable workflow: authoritative sources
  to prefer (official ministry/state portals and MyScheme), one Markdown file
  per verified scheme, matching `data/scheme_catalog.json` entries with stable
  `source_file`/id, how to validate and re-ingest, and the hard boundaries:
  **never scrape/copy content without respecting terms/robots.txt and never
  fabricate missing eligibility**.
- **`docs/scheme-record-template.md`** — the per-scheme Markdown template
  (source URL, jurisdiction, `last_verified`, `data_status`, eligibility,
  exclusions, benefits, documents, application steps, "not official advice"
  boundary). It lives in `docs/`, **outside `data/`**, so it is never ingested.
- **`scripts/validate_data.py`** — dependency-free (stdlib-only) validator:

  ```bash
  python scripts/validate_data.py
  ```

  It exits non-zero with explained errors when: the state/UT count is not
  exactly 36 (28 + 8); a state Markdown or catalog entry is missing; a catalog
  `source_file` does not exist; `data_status` is not one of the allowed values
  (`sample_verified`, `directory_seed`); an official/source URL is not `https`;
  or a catalog id/source file is duplicated. On success it prints a compact
  summary. It also parses every `*.json` under `data/` and `eval/`.

### Protected ingestion and bounded inputs

- `POST /ingest` requires the **`X-Admin-Token`** header matching `ADMIN_TOKEN`
  (compared with `secrets.compare_digest`; tokens are never logged). With no
  `ADMIN_TOKEN` configured it returns **503 "disabled"** — a public
  unauthenticated re-ingest endpoint is not acceptable. Startup auto-ingestion
  is unchanged and idempotent.
- `QueryRequest.question` is bounded to **2–2,000 characters** (whitespace-only
  input is rejected); free-text profile/goals fields are non-empty, length-
  capped, and the whole profile payload has a serialized-size cap. All bounds
  return normal **HTTP 422** validation errors. Query text and profile data are
  never stored in logs.
- Live Groq answers are capped at **`max_tokens=1024`** (`app/rag.py`), so a
  public free-tier response can never consume unbounded output tokens.

### Evaluation

`eval/questions.json` now also includes: a question about nationwide/state
directory discovery, a **profile-aware** case (the harness passes an optional
per-case `profile` and `language` through to the production pipeline), and a
**Hindi** case. The existing six-scheme cases and the out-of-domain failure case
are preserved. Directory-seed results are reported with the same honesty
threshold — a `directory_seed` chunk is never treated as a verified eligibility
decision by the scoring harness. No scores were fabricated in this iteration;
regenerate them by running `python -m eval.run_eval` (see the Evaluation
section).

## Local development

1. Copy the env file and set your key:
   - `cp .env.example .env` (Windows: `copy .env.example .env`)
   - Set `GROQ_API_KEY=...` and change `DATABASE_URL` host from `db` to `localhost`.
2. Create a virtualenv and install dependencies:
   - `python -m venv .venv` and activate it
   - `pip install -r requirements.txt`
3. Start only the database:
   - `docker compose up -d db`
   - Note: the `db` service does not publish port 5432 by default. To reach it
     from a locally running uvicorn, temporarily add `ports: - "5432:5432"` to the
     `db` service, or run the whole stack in Docker.
4. Run the API:
   - `uvicorn app.main:app --reload`
   - Docs at http://localhost:8000/docs, Streamlit at http://localhost:8501.

## GROQ_API_KEY

The only external API in the stack is Groq for LLM inference. Get a free key at
https://console.groq.com. Embeddings, chunking, and vector storage all run locally.

- **Demo fallback (no key):** if `GROQ_API_KEY` is blank, invalid, rate-limited,
  or Groq is otherwise unavailable, `/query` does not fail - it returns HTTP 200
  with a pre-made demo answer. The response is clearly labelled `"mode": "demo"`
  with a `notice` field, and the Streamlit UI shows the notice, so the answer is
  never presented as a live Groq result.
- **Live RAG (with key):** set `GROQ_API_KEY` in `.env`, then restart the API
  container (`docker compose restart api`). Responses then come from the real
  pgvector retrieval + `ChatGroq` pipeline and are labelled `"mode": "live"`.

Demo fallback covers these sample topics (facts match `data/schemes/*.md`):

- PM-KISAN income support and instalments, and who is excluded
- Ayushman Bharat PM-JAY health cover
- PMAY-G financial assistance
- PM-SYM pension
- Startup India DPIIT recognition eligibility
- GST introduction and registration thresholds

Example questions that work in demo mode:

- "How much income support does PM-KISAN provide and in what instalments is it paid?"
- "Who is excluded from receiving PM-KISAN benefits?"
- "What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?"
- "How much financial assistance does PMAY-G provide for building a pucca house?"
- "What monthly pension does PM-SYM provide and at what age does it start?"
- "What are the eligibility conditions for DPIIT startup recognition under Startup India?"
- "What is the GST registration turnover threshold for goods and for services?"

Any other question returns the generic demo record, which explains that a real
Groq key is needed for live answers.

## Evaluation

RAGAS-based offline evaluation measures **faithfulness** and **answer
relevancy** of the retrieval + answer pipeline over the curated cases in
`eval/questions.json`. Judge LLM calls reuse `app.rag.get_llm()` (Groq free
tier) and judge embeddings reuse `app.db.get_embeddings()` (local
`all-MiniLM-L6-v2`), so no OpenAI or paid embedding API is involved.

> **Important:** the demo fallback is *not* a measured RAGAS result. The
> harness still requires a real `GROQ_API_KEY` and exits clearly without one -
> the pre-made demo answers are never evaluated or reported as scores.

> **RAGAS pin:** RAGAS is pinned at **0.2.15** for verified compatibility with
> the pinned `langchain==0.3.21`. Run it in a trusted local/evaluation
> environment against the curated text-only dataset in `eval/questions.json`
> (it is not part of the production image). Future upgrades - especially to
> RAGAS 0.3.x - must be tested for API and security compatibility across the
> whole harness before adoption.

Prerequisites:

- Install the evaluation-only dependencies in your local environment:
  `pip install -r requirements-eval.txt` (this also installs
  `requirements.txt`). RAGAS and its transitive packages are intentionally not
  part of the production image.
- The database must be running and ingested (`docker compose up -d db`, or the
  full stack), so the vector store is reachable from where you run the command.
- A valid `GROQ_API_KEY` in your environment or `.env` (free tier is fine).
  RAGAS judge calls consume Groq free-tier quota, so keep runs small.

Run a cheap check (first 3 questions):

```bash
python -m eval.run_eval --limit 3
```

Run the full set:

```bash
python -m eval.run_eval
```

Generated files (the command creates `eval/results/` if needed):

- `eval/results/report.md` - publishable Markdown report with run timestamp,
  aggregate and per-question scores, and a **Failure Cases** section.
- `eval/results/scores.json` - machine-readable per-question and aggregate
  scores.

A failure case is any question whose `faithfulness` or `answer_relevancy`
score is below **0.70**, or a case where evaluation errored. The 0.70
threshold is a project triage threshold for spotting regressions, not a
universal quality claim.

**Data-ops note:** `eval/results/report.md` is the publishable report and is
tracked in version control. The machine-readable `eval/results/*.json` and
`eval/results/*.csv` artifacts are transient (they change on every run) and
are intentionally ignored by `.gitignore`; regenerate them by re-running the
command.

## Deployment on a free VPS

A simple, self-hosted Docker deployment: three containers (Postgres/pgvector,
FastAPI, Streamlit) on plain Docker Engine + the Compose plugin. No cloud SDKs,
no managed services, no reverse proxy - it runs on almost any Linux VPS.

> **Free-tier availability and quotas vary** by provider and change over time;
> this runbook makes no provider-specific assumptions. It uses Ubuntu-style
> commands, which work on most free-tier VPS images. Examples like Oracle Cloud
> "Always Free" (or any comparable provider) are fine.
>
> **Minimum hardware: at least 2 GB RAM and ~20 GB disk.** The API image runs
> PyTorch and downloads the local sentence-transformers embedding model
> (`all-MiniLM-L6-v2`, ~90 MB), so tiny 1 GB instances are unreliable and may
> be OOM-killed during first start or first queries. A free-tier ARM instance
> with 4 GB RAM / 24 GB disk is a comfortable fit.

> **CPU-only embeddings by design.** The API image installs a CPU-only PyTorch
> wheel from the official PyTorch CPU index (`requirements-api.txt` pins
> `torch==2.6.0+cpu` via `--extra-index-url https://download.pytorch.org/whl/cpu`),
> so `docker compose build` never pulls the multi-gigabyte CUDA-enabled `torch`
> wheel from PyPI. This keeps free-VPS builds small and fast. Sentence
> transformers run locally on the CPU exactly as in local development, so the
> application embedding API is unchanged.

### 1. Provision and firewall

| Port | Service | Firewall |
| --- | --- | --- |
| 22 | SSH | open to your IP (or restrict to trusted IPs) |
| 8501 | Streamlit web UI | open to the public (or restrict as you like) |
| 8000 | API | **optional / private** - keep closed publicly; reach via SSH tunnel (step 5) |
| 5432 | PostgreSQL | **never open** - Docker does not publish it; keep it that way |

Apply the rules in the **provider's firewall** (cloud security list / network
security group) and, if your distribution enables it, the **host firewall**:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8501/tcp
sudo ufw enable
```

### 2. Install Docker Engine + Compose plugin

Follow the provider's / distro's **official** Docker Engine instructions (do
not install the distro's `docker` apt package, which is usually outdated). A
concise Ubuntu path:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in (or run `newgrp docker`) so the group takes effect.
docker --version
docker compose version
```

### 3. Clone/upload the project

```bash
git clone <your-repo-url> scheme-gpt
cd scheme-gpt
cp .env.example .env
```

Uploading instead of cloning? Copy the whole project folder (excluding `.git`,
`.venv`, `__pycache__` and `.env`), e.g.
`scp -r ./SchemeGPT user@<vps-ip>:/home/user/scheme-gpt`.

Then in `.env` on the VPS:

- Leave `GROQ_API_KEY=` blank for the pre-made demo, or set a real free-tier
  key at https://console.groq.com for live RAG answers. A blank/invalid key
  never breaks the stack - `/query` falls back to clearly-labelled demo answers.
- Keep `DATABASE_URL` on the `@db:5432/...` host (internal docker network).
- Leave `STREAMLIT_API_URL` unset - compose sets `http://api:8000` for the web
  container automatically.

### 4. Start the stack

```bash
docker compose up -d --build
```

The first start downloads base images, installs Python dependencies and pulls
the embedding model, so it can take several minutes. The API healthcheck
deliberately waits (`start_period: 300s`) before judging the API unhealthy;
later starts are fast. All containers restart automatically if they crash
(`restart: unless-stopped`).

### 5. Verify

```bash
docker compose ps
docker compose logs -f api          # Ctrl-C stops following
curl http://localhost:8000/health   # expect {"status":"ok"}
```

- **Public UI:** `http://<YOUR_VPS_IP>:8501`
- **API docs:** the API port binds to the VPS's localhost only. Reach it from
  your laptop over SSH:

  ```bash
  ssh -L 8000:localhost:8000 user@<YOUR_VPS_IP>
  ```

  then open http://localhost:8000/docs locally (or run
  `curl http://localhost:8000/docs` directly on the VPS).

### 6. Operations

- **Live key update:** edit `.env` on the VPS, then `docker compose restart api`.
  A blank/invalid key simply falls back to the labelled demo - the stack keeps
  running either way.
- **Updates:** `git pull` (or re-upload), then `docker compose up -d --build`.
- **Persistence:** vectors live in the named volume `pgdata`. The API
  auto-ingests `data/schemes/*.md` only when the vector store is empty, so
  restarts do not re-ingest.
- **Safe stop:** `docker compose down` stops and removes containers but keeps
  `pgdata`. **Never** use `docker compose down -v` unless you want to delete
  the vector store.
- **Backup (simple pg_dump):**

  ```bash
  docker compose exec db pg_dump -U scheme -d schemegpt > schemegpt_$(date +%F).sql
  ```

  Restore with
  `docker compose exec -T db psql -U scheme -d schemegpt < backup.sql`.

### 7. Operational warnings

- This is a **portfolio/demo deployment**: there is **no login/account auth or
  rate limiting** on the UI or API, and PostgreSQL is reachable from any
  container in the network. Do not upload sensitive documents.
- **Coverage is honest, not exhaustive:** the corpus maps all 36 state/UT
  jurisdictions, but only **six central schemes are verified samples**
  (`sample_verified`). State/UT entries are `directory_seed` discovery entries
  — they link to the official national MyScheme discovery portal and are not
  verified eligibility decisions. Always verify scheme-level eligibility on the
  official source link before applying.
- **Saved profiles use a private save code, not a login account.** The one-time
  access code is returned exactly once, only its SHA-256 hash is stored, and it
  is required for all read/update/delete calls. Do **not** enter Aadhaar numbers
  or sensitive documents in profiles or questions.
- **Hindi and scenario/profile workflow:** the UI and `/query`,
  `/recommendations` support an `en`/`hi` toggle; profiles tailor guidance and
  can be saved/restored with the private save code.
- **Manual re-ingestion is token-protected:** `POST /ingest` requires
  `ADMIN_TOKEN` via the `X-Admin-Token` header and returns 503 when no token is
  configured. Startup auto-ingestion remains automatic and idempotent.
- Free Groq quota and the VPS's CPU/RAM are shared and can be exhausted -
  expect occasional rate-limit fallbacks to demo mode under heavy use.
- Before any public production use, put the UI behind HTTPS (e.g. a reverse
  proxy with TLS) and add authentication.
- Keep the OS packages and Docker updated.

### 8. Troubleshooting

- **API container unhealthy:** check `docker compose logs api`. On first start
  the embedding model download / auto-ingestion can exceed the healthcheck's
  `start_period` on slow connections - wait and re-check `docker compose ps`.
- **Embedding / memory errors:** on low-memory instances the API is often
  OOM-killed (check `dmesg | tail` or `journalctl`). Retry
  `docker compose up -d --build` on a stable connection and confirm the VPS
  has at least 2 GB RAM.
- **Bad/blank key shows demo answers:** by design. Blank, invalid, rate-limited
  or unavailable keys fall back to clearly-labelled demo responses. Set a valid
  `GROQ_API_KEY` and `docker compose restart api` for live answers.
- **Cannot reach the UI on 8501:** confirm the provider firewall *and* host
  firewall allow 8501, that `docker compose ps` shows `web` as running, and
  that you use `http://<VPS_IP>:8501` (not https). The API on 8000 is bound to
  localhost by design - use the SSH tunnel from step 5.

## Smoke check

Cheap, key-free checks to run locally or on the VPS before/after deployment:

```bash
# 1. Every Python file compiles
python -m py_compile app/*.py streamlit_app.py scripts/validate_data.py eval/run_eval.py

# 2. Data validation (stdlib-only; parses every JSON, checks the 36/42 corpus)
python scripts/validate_data.py

# 3. The compose file resolves (healthchecks, dependencies, volumes, ports)
docker compose config --quiet

# 4. With the stack running, the API is healthy (no Groq key needed)
curl http://localhost:8000/health   # -> {"status":"ok"}
curl http://localhost:8000/coverage # -> {"jurisdiction_count":36, ...}
```

With a blank key the stack starts normally, `/query` returns the labelled
pre-made demo answer, and the Streamlit UI shows the demo notice - so the
smoke check works entirely without a Groq key. `POST /ingest` without an
`X-Admin-Token` returns 503 (disabled) when `ADMIN_TOKEN` is blank.
