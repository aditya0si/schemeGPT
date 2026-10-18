# Deploying SchemeGPT as a hosted website

This is the free-tier runbook for a live, public deployment: **Vercel** (Next.js
web) + **Render** (FastAPI API, `Dockerfile.render`) + a **Vercel function**
(the query embedder) + **Postgres with pgvector** (Neon, or the database
`render.yaml` creates). Everything below is executable without paid accounts.
The Docker-Compose VPS runbook remains in the main README as the self-hosted
alternative.

> **This document used to describe a Fly.io path. That path is superseded**, and
> `https://schemegpt-api.fly.dev` no longer resolves. The historical steps are
> kept at the bottom under "Superseded: the Fly.io path (history, not
> instructions)" because the reasons it was abandoned are the interesting part —
> but do not follow them.

Architecture on hosted tiers:

```
Browser ──> Vercel (Next.js web, /api/chat/stream proxy)
                 │ server-side fetch (browser never talks to the API)
                 ▼
            Render (FastAPI, Dockerfile.render, 512 MB free instance)
                 │  query text
                 ▼
            Vercel function (deploy/schemegpt-embedder → 384-dim int8 ONNX)
                 ▼
            Postgres + pgvector  +  Groq API (LLM)
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

## 3. Render — the API

1. In the Render dashboard: **New → Blueprint**, pick this repository, **Apply**.
   `render.yaml` defines the `schemegpt-api` web service and its database.
2. The blueprint builds `./Dockerfile.render`, which runs the **same**
   `intfloat/multilingual-e5-small` model through ONNX Runtime with the int8
   graph baked into the image at build time — the fp32 image needs ~1–2 GB of
   resident memory and a free instance has 512 MB.
3. Because even the int8 session cannot sit beside the app inside 512 MB
   (measured in `deploy/schemegpt-embedder/README.md`: the first live query was
   OOM-killed at `oomKilled 512Mi`), point query embedding at the Vercel function
   from §4 instead of embedding in-process:
   ```
   EMBEDDING_BACKEND=remote
   EMBEDDING_API_URL=https://<your-embedder>.vercel.app/embed
   EMBEDDING_MODEL=intfloat/multilingual-e5-small      # unchanged
   ```
4. Set `GROQ_API_KEY` (leave it blank and the service serves its labelled demo
   answers — a supported mode, not a failure) and `DATABASE_URL` from step 1.
5. Verify: `https://<service>.onrender.com/readyz` reports `status: ready`, the
   configured mode, vector count, complete active corpus generation, and
   embedding-model compatibility; then confirm `GET /coverage` reports the
   scaled corpus. `render.yaml` sets the platform health check to `/livez`
   (process liveness only) so a cold-starting instance is not killed for
   dependency checks.

Notes:
- The free instance suspends when idle. The first request after a suspend pays a
  cold start — measured at 25 s+ for the first `/livez` of a suspended instance
  in `docs/portfolio-readiness-assessment.md` §2.1. Budget for it; the web app's
  `/` still renders because its coverage fetch times out at 2 s
  (`web/app/page.tsx`).
- Groq free-tier rate limits are shared: the API's per-IP rate limiter
  (`RATE_LIMIT_RPM`, default 20/min) and semantic cache (on by default) keep a
  public deployment inside quota. Set `RATE_LIMIT_RPM=0` to disable.

## 4. Deploy the query embedder (Vercel function)

`deploy/schemegpt-embedder/` is a self-contained Vercel function that serves
384-wide vectors for query text. It is not meant to be a public embedding
service: set `EMBED_TOKEN` on the function and `EMBEDDING_API_KEY` on the API to
lock it down. Its contract, memory measurements and wiring are in
`deploy/schemegpt-embedder/README.md`.

```bash
curl https://<your-embedder>.vercel.app/health
# {"status":"alive","model":"intfloat/multilingual-e5-small","width":384,"loaded":false}
```

## 5. Vercel — the web app

1. Push the repo to GitHub (the web app is `web/`).
2. In Vercel: **Add New Project** → import the repo → set:
   - **Root Directory:** `web`
   - Framework preset: Next.js (auto-detected)
   - **Environment variable:** `API_URL = https://<service>.onrender.com`
     (server-side env var; no `NEXT_PUBLIC_` prefix needed since the proxy
     runs on the server).
3. Deploy. The site is live at `https://<project>.vercel.app`.
4. `/evidence` and `/coverage` are routes inside the same Next.js app — they need
   no extra deployment step and add no endpoint. `/coverage` reads
   `GET /coverage` server-side through `API_URL`; `/evidence` reads only
   committed data and therefore works even when the API is asleep.

## 6. Post-deploy checklist

```bash
curl https://<embedder>.vercel.app/health            # {"status":"alive","width":384,...}
curl https://<service>.onrender.com/livez            # {"status":"alive"}
curl https://<service>.onrender.com/readyz           # dependency readiness + live/demo mode
curl https://<service>.onrender.com/metrics          # counters, cache hit rate, tokens, USD cost
curl -X POST https://<service>.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"question":"How much income support does PM-KISAN provide?"}'
# expect "mode":"live" with sources; demo mode means GROQ_API_KEY is unset/wrong
```

Then load the site, ask a question, confirm tokens stream and quotes render, and
confirm `/evidence` and `/coverage` both answer `200` — with the API asleep,
`/evidence` must still render its four measured cards, and `/coverage` must show
its explicitly labelled unavailable state rather than a blank page.

## Operational notes

- **Secrets:** `.env` is git-ignored and never deployed; Render environment
  variables / Vercel env vars carry credentials. Rotate the Groq key if it was
  ever committed.
- **DB migration:** the maintained `langchain-postgres` adapter writes to the
  application-owned `scheme_docs_v2` table. Existing legacy `langchain_pg_*`
  tables are left untouched for rollback; remove them only after validation.
  The semantic cache owns `query_cache` separately.
- **Re-ingestion:** repeat step 2 after corpus changes, then restart the API
  service from the Render dashboard.
- **Costs at free tier:** ~0.5 GB storage (vectors for this corpus fit), Render
  ~zero when suspended, Vercel hobby free, Groq free tier rate-limited.

## Superseded: the Fly.io path (history, not instructions)

**What it was.** The original hosted topology ran the API on Fly.io with the
**main** `Dockerfile` (PyTorch plus a baked fp32 `multilingual-e5-small`), and
the Vercel web app pointed `API_URL` at `https://schemegpt-api.fly.dev`.

**Why it was abandoned.** Two measured reasons, not preferences:

1. The fp32 image wants ~1–2 GB of resident memory. On a 512 MiB free instance
   the first query that loaded the model was OOM-killed (`server_failed`,
   `oomKilled 512Mi`) — recorded with per-component peaks in `Dockerfile.render`
   and `deploy/schemegpt-embedder/README.md`.
2. `schemegpt-api.fly.dev` no longer resolves (probe: `HTTP 000`, DNS failure —
   `docs/portfolio-readiness-assessment.md` §1). A runbook whose hosts do not
   resolve is worse than no runbook, which is why this document now describes
   Render.

**The old commands, kept verbatim so the history stays checkable — do not run
them against this repository:**

```text
fly launch --no-deploy --copy-config
fly secrets set GROQ_API_KEY=... DATABASE_URL="postgresql+psycopg://<url>"
fly deploy
curl https://schemegpt-api.fly.dev/readyz
API_URL = https://schemegpt-api.fly.dev        # Vercel env var
fly apps restart schemegpt-api                 # after re-ingestion
```

`fly.toml` is still in the repository for the same reason: it is the record of
that deployment, not a supported target. The supported topology is
`render.yaml` + `Dockerfile.render` + `requirements-render.txt` +
`deploy/schemegpt-embedder/`.
