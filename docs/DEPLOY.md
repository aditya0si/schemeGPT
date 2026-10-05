# Deploying SchemeGPT as a hosted website

This is the free-tier runbook for a live, public deployment: **Vercel**
(Next.js web) + **Fly.io** (FastAPI API) + **Neon** (serverless Postgres with
pgvector). Everything below is executable without paid accounts. The
Docker-Compose VPS runbook remains in the main README as the self-hosted
alternative.

Architecture on hosted tiers:

```
Browser ──> Vercel (Next.js web, /api/chat/stream proxy)
                 │ server-side fetch (browser never talks to the API)
                 ▼
            Fly.io (FastAPI, Dockerfile, 2 GB)
                 ▼
            Neon Postgres (pgvector)  +  Groq API (LLM)
```

The web app proxies all API traffic server-side (`web/app/api/chat/stream/route.ts`),
so the API never needs public CORS and no browser origin allowlist changes.

## 1. Neon — Postgres with pgvector (free tier)

1. Create an account at https://neon.tech and a new project (e.g. `schemegpt`).
2. In the SQL editor enable the extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy the pooled connection string; it looks like
   `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb`.
4. The app needs the SQLAlchemy form — note the `+psycopg` driver segment:
   `postgresql+psycopg://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb`

## 2. Populate the vector store (one command from your machine)

The API builds its index on first start, but for a corpus this size you want
to control it explicitly. From the repo root with your local `.venv`:

```bash
DATABASE_URL="postgresql+psycopg://<neon-pooler-url>" \
  python scripts/reembed.py --yes
```

That ingests `data/schemes`, `data/states` and `data/myscheme` with the
configured embedding model. Verify:

```bash
psql "<neon-url>" -c "SELECT count(*) FROM scheme_docs_v2;"
```

## 3. Fly.io — the API

1. Install `flyctl` (https://fly.io/docs/flyctl/install/), `fly auth login`.
2. From the repo root (config is already in `fly.toml`):
   ```bash
   fly launch --no-deploy --copy-config
   fly secrets set GROQ_API_KEY=... \
     DATABASE_URL="postgresql+psycopg://<neon-pooler-url>"
   fly deploy
   ```
3. Verify: `https://schemegpt-api.fly.dev/readyz` reports `status: ready`,
   the configured mode, vector count, complete active corpus generation, and
   embedding-model compatibility; then confirm `GET /coverage` reports the
   scaled corpus.
4. Optional: a custom domain via `fly certs add`.

Notes:
- The image bakes the `multilingual-e5-small` model (~470 MB), so deploys are
  slow the first time and fast afterwards.
- `auto_stop_machines = "suspend"` keeps costs at zero when idle; the first
  request after a suspend pays a few seconds of cold start.
- Groq free-tier rate limits are shared: the API's per-IP rate limiter
  (`RATE_LIMIT_RPM`, default 20/min) and semantic cache (on by default) keep
  a public deployment inside quota. Set `RATE_LIMIT_RPM=0` to disable.

## 4. Vercel — the web app

1. Push the repo to GitHub (the web app is `web/`).
2. In Vercel: **Add New Project** → import the repo → set:
   - **Root Directory:** `web`
   - Framework preset: Next.js (auto-detected)
   - **Environment variable:** `API_URL = https://schemegpt-api.fly.dev`
     (server-side env var; no `NEXT_PUBLIC_` prefix needed since the proxy
     runs on the server).
3. Deploy. The site is live at `https://<project>.vercel.app`.

## 5. Post-deploy checklist

```bash
curl https://<api>.fly.dev/livez          # {"status":"alive"}
curl https://<api>.fly.dev/readyz          # dependency readiness + live/demo mode
curl https://<api>.fly.dev/metrics         # counters, cache hit rate, tokens
curl -X POST https://<api>.fly.dev/query \
  -H "Content-Type: application/json" \
  -d '{"question":"How much income support does PM-KISAN provide?"}'
# expect mode":"live" with sources; demo mode means GROQ_API_KEY is unset/wrong
```

Then load the site, ask a question, confirm tokens stream and quotes render.

## Operational notes

- **Secrets:** `.env` is git-ignored and never deployed; Fly secrets / Vercel
  env vars carry credentials. Rotate the Groq key if it was ever committed.
- **DB migration:** the maintained `langchain-postgres` adapter writes to the
  application-owned `scheme_docs_v2` table. Existing legacy `langchain_pg_*`
  tables are left untouched for rollback; remove them only after validation.
  The semantic cache owns `query_cache` separately.
- **Re-ingestion:** repeat step 2 after corpus changes, then restart the API
  (`fly apps restart schemegpt-api`).
- **Costs at free tier:** Neon ~0.5 GB storage (vectors for this corpus fit),
  Fly ~zero when suspended, Vercel hobby free, Groq free tier rate-limited.
