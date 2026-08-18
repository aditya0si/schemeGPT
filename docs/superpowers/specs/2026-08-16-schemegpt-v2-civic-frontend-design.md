# SchemeGPT v2 — Engineered-Editorial Frontend and Measured Retrieval Upgrades

- **Date:** 2026-08-16
- **Status:** approved in brainstorming session; amended same day per user direction
  (aesthetic reference: https://haoqi.design/, plus RAG answer-style requirements)
- **Goals:** improve SchemeGPT in both functionality and aesthetics, serving a mix of
  **portfolio craft** (demonstrable engineering quality) and **product usefulness**
  (genuinely helpful to citizens navigating Indian government schemes)

## Decisions locked during brainstorming

| Decision | Choice |
| --- | --- |
| Primary goal | Mix of portfolio + product |
| UI strategy | Rebuild as a custom frontend (replace Streamlit eventually) |
| Scope of rebuild | Full parity with today's features **plus** a scheme browser |
| Aesthetic direction | **Engineered editorial** (reverse-engineered from haoqi.design): warm cream paper, oversized uppercase grotesk display, terminal-mono chrome and blinking caret, zero border-radius, semantic accent colors, honesty stamps |
| Sequencing | Vertical slices, each independently demo-able |
| Stack | Next.js (App Router) + Tailwind CSS, React, served as a new `web` compose service |
| Cost posture | Unchanged: Groq free tier, local embeddings, Docker on a small (≥2 GB) VPS |

### Product voice for the RAG pipeline (user requirement, 2026-08-16)

People ask in imperfect, broken, or colloquial language (English, Hindi, Hinglish
mixed). The system must: **(1) normalize** the question internally into a clean
retrieval query, **(2) retrieve** from the scheme/law corpus, **(3) answer in plain,
spoken-style human language**, and **(4) quote** the exact policy/scheme statements it
relies on, clearly attributed with source and verification status. This behaviour is
part of Slice 1's backend work (prompt redesign + query normalization step), not a
later slice.

> Implementation is planned and executed **one slice at a time**: each slice below
> gets its own implementation plan, starting with Slice 1.

## Non-goals (explicitly out of scope)

- Real account authentication (passwords, sessions, OAuth) — remains a future iteration.
- Corpus expansion beyond the current 42 records — that is editorial data-ops work
  (already documented in `docs/data-operations.md`), not code. The scheme browser is
  designed to make a grown corpus presentable, but growing it is not part of this program.
- Rate limiting or production hardening beyond the current posture.
- Dark mode. Light "paper" theme only.
- Any change to the honesty semantics: demo fallback labelling, `data_status`
  provenance, coverage transparency, and the verification disclaimer are preserved
  exactly on every new surface.

## Current-state baseline (what v2 builds on)

- FastAPI (`app/`): `/health`, `/query`, `/states`, `/profiles`, `/recommendations`,
  `/coverage`, token-protected `POST /ingest`; bounded inputs; demo fallback.
- pgvector store with local `all-MiniLM-L6-v2` embeddings; LangChain
  `create_retrieval_chain` retrieval; Groq `llama-3.3-70b-versatile` LLM.
- Streamlit UI (`streamlit_app.py`, ~1,900 lines): chat, profiles, recommendations,
  en/hi toggle, coverage pill.
- RAGAS eval (12 cases): faithfulness **0.950**, answer relevancy **0.774**.
  Known failure cases: profile-aware question scored **0.000** relevancy (case 11);
  several faithfulness scores missing due to judge timeouts.
- No pytest suite; smoke checks are `py_compile`, `scripts/validate_data.py`, and
  `docker compose config --quiet`.

## Slice 1 — App shell + streaming chat

**Backend.** New SSE endpoint `POST /query/stream` (same request schema and bounds as
`/query`). It streams, in order: a `sources` event (retrieved chunks with metadata),
then `token` events as the answer generates, then a final `done` event carrying the
mode (`live`/`demo`), notice, and any disclaimer. Implementation uses the LangChain
chain's async streaming against Groq. In demo mode the pre-made answer is streamed
word-by-word with the same `"mode": "demo"` labelling, so no-key behaviour remains
clearly distinguishable. Mid-stream errors emit an `error` event and close the stream;
the client keeps partial text and appends a labelled failure notice. The existing
`/query` JSON endpoint stays unchanged for API consumers and the eval harness.

**RAG answer style and question normalization (live mode).** The live pipeline is
reworked to match the product voice above: **(1)** a normalization step rewrites the
user's raw question (broken English, Hindi, Hinglish, colloquial phrasing) into a
clean retrieval query before vector search — one cheap LLM call with a strict
"output only the rewritten question" instruction, falling back to the raw question
on any error, timeout, or empty result; **(2)** the answer prompt instructs the model
to reply in plain, spoken-style language a citizen understands, and to quote the
exact scheme/policy statements it relies on as attributed blockquotes (source name +
`data_status`), never inventing quotes not present in retrieved context; **(3)** the
normalization never changes the language the user asked in — a Hindi question gets a
Hindi answer. Demo-mode answers are unchanged. The normalization step is measured in
Slice 4's RAGAS pass alongside retrieval work.

**Frontend.** New `web/` directory: Next.js App Router + Tailwind. This slice delivers
the design system (tokens below) and the chat page: hero with coverage pill, message
history, streaming assistant messages with a typing indicator, ruled source cards with
verification stamps, live/demo mode banner, en/hi toggle, and a footer disclaimer.
Client-side chat talks to the API via SSE with abort handling (stop button).

**Compose.** New `web` service (Node) alongside `api`; `STREAMLIT_API_URL` is renamed
to `API_URL` in compose with the old name still honoured during migration. Streamlit
keeps running until Slice 5.

**Done when:** a user can chat with streaming answers in both live and demo modes, in
English and Hindi, with sources and stamps, in the new UI served from compose.

## Slice 2 — Scheme browser

**Backend.** New read-only `GET /schemes` endpoint over `data/scheme_catalog.json`
plus the per-scheme Markdown records: returns id, name, jurisdiction, category,
`data_status`, one-line summary, `source_url`, `last_verified`, and scheme facts
(eligibility, exclusions, benefits, documents, application steps) for detail views.
Query params filter by jurisdiction, category, and `data_status`. `/states` and
`/coverage` are unchanged.

**Frontend.** `/schemes` — a filterable, searchable list (36 jurisdictions, 6 verified
samples today). `/schemes/[id]` — a server-rendered detail page with full scheme facts,
prominent verification stamp, official-source link, and the not-official-advice
boundary. Verified schemes and directory seeds are visually distinct treatments; a
directory seed page shows the discovery/MyScheme framing, never eligibility claims.
Server rendering makes scheme pages indexable by search engines — the product-side
payoff of Next.js.

**Done when:** a citizen can browse and filter all catalog records and open a shareable,
indexable detail page whose honesty framing matches the chat.

## Slice 3 — Profiles + recommendations

Port the existing Streamlit flows to the new frontend against the **unchanged**
`/profiles` and `/recommendations` endpoints. All careful semantics are preserved:
every profile field optional; "Not specified / Prefer not to say" defaults for area and
disability; `None` sent unless explicitly chosen; language switch never mutates stored
values; save code shown exactly once with copy affordance; profile required via
`X-Profile-Token` for read/update/delete; explainable recommendation signal chips; the
verification disclaimer on every recommendation result. Field-level 422 messages
(ported from the Streamlit `_validation_msgs` logic).

**Done when:** full profile create/load/update/delete and recommendation flows work in
the new UI with identical API semantics and clearer presentation.

## Slice 4 — Retrieval quality, measured

1. **Fix profile-aware answering.** Diagnose why the profile-aware eval case (case 11)
   scores 0.000 relevancy; ensure profile context reaches the RAG prompt template
   explicitly (persona/scenario block), not just retrieval. Re-measure.
2. **Retrieval upgrade, chosen by measurement.** Candidates: hybrid retrieval
   (pgvector cosine + Postgres `tsvector` full-text, fused with reciprocal rank
   fusion), MMR diversification, and/or multi-query rewriting. Run RAGAS on each
   candidate over the 12-case set; adopt only what measurably improves aggregate
   relevancy without degrading faithfulness or out-of-domain honesty.
3. **Publish the delta.** Update `eval/results/report.md` with before/after numbers
   and a dated note describing the change; keep the 0.70 triage threshold.
4. **Add a pytest suite** (new `tests/`): request-validation bounds (2–2,000 chars,
   profile caps), profile token flow (create → read/update/delete with and without
   token), recommendation determinism and disclaimer presence, `/schemes` filtering
   contract, `/query/stream` event sequence in demo mode, and demo-fallback labelling.
   Suite runs without Groq or a live LLM (demo mode + mocked chain).

**Done when:** RAGAS shows a dated, reproducible improvement (including the
profile-aware case passing), and `pytest` passes as part of the smoke check.

## Slice 5 — Retire Streamlit

## Addendum (2026-08-19): AI-engineering hardening track

User-approved track of seven improvements, implemented in order after Slice 1
(scheme browser slices may interleave later). Honesty semantics and the
`/query` response shape remain stable; `/query/stream` may gain additive
events (`quotes`, `step`).

1. **Multilingual embeddings** — swap `all-MiniLM-L6-v2` for
   `intfloat/multilingual-e5-small` (same 384-dim, E5 query/passage prefixes)
   with `scripts/reembed.py` migration + startup mismatch warning. Fixes weak
   Devanagari retrieval for the actual audience.
2. **Structured quotes with verification** — server-side parsing of the
   `> quote [source, data_status]` lines, programmatic verification against
   retrieved context (normalized containment or ≥0.85 similarity), emitted as
   a `quotes` SSE event; unverified quotes are flagged, never silently kept.
3. **Hybrid retrieval + reranking** — Postgres `tsvector` FTS fused with
   vector search via reciprocal rank fusion (k=60); optional CPU cross-encoder
   reranker (`BAAI/bge-reranker-base`) behind `ENABLE_RERANKER` (RAM-bound
   VPSes keep it off).
4. **Evaluation as a regression gate** — expanded golden set (Hinglish,
   Hindi, comparative, quote-format, out-of-domain), RAGAS
   context-precision/recall added, per-run history (`history.jsonl`), and a
   `--gate` mode failing below floors (faithfulness ≥ 0.85, relevancy ≥ 0.70).
5. **Agentic multi-step retrieval** — heuristic router sends comparative /
   multi-scheme / profile-aware questions to a Groq tool-calling loop
   (tools: `search_schemes`, `get_scheme_details`, `list_jurisdictions`; max 3
   tool iterations) that gathers context across steps, then streams the final
   answer like the single-shot path; `step` events expose each tool call.
6. **Observability** — `app/metrics.py` in-process counters + latency
   percentiles exposed at `GET /metrics`; LangSmith tracing documented as
   env-only opt-in.
7. **Model routing** — `GROQ_FAST_MODEL` (default `llama-3.1-8b-instant`)
   for normalization/small tasks; `GROQ_MODEL` (70b) reserved for answers and
   the agent loop.

Remove the Streamlit compose service and `Dockerfile.streamlit`; keep
`streamlit_app.py` in repo history for reference. Update README (architecture,
quickstart, VPS runbook ports — new UI port replaces 8501) and the smoke check.
Preserve a documented one-commit rollback path (git history) rather than keeping both
UIs running.

**Done when:** `docker compose up` serves only the new UI; README and runbook match
reality; smoke check passes.

## Architecture after v2

```
db (pgvector/pg16, no published port)
 └─ api (FastAPI + uvicorn, localhost:8000 published)
     └─ web (Next.js server, public port; SSR pages + client chat via SSE)
streamlit (until Slice 5, unchanged)
```

- Next.js server components and route handlers call the API over the internal Docker
  network (same pattern as today's Streamlit container). **The browser only ever talks
  to `web`:** chat SSE is proxied through a Next.js route handler that pipes the API's
  `/query/stream` response, so the API stays localhost-only in deployment exactly as
  today.
- Env: `API_URL` (internal base URL), `GROQ_API_KEY`, `ADMIN_TOKEN`,
  `DATABASE_URL` — all existing values and fallbacks unchanged.
- No changes to ingestion, pgvector schema (except any index the retrieval upgrade
  needs), embeddings model, or admin-token protection.

## Design system (engineered editorial, from haoqi.design)

Reverse-engineered reference points (haoqi.design, inspected 2026-08-16): cream
`#FBFAF4` body on pure black text, secondary paper `#EFEDE7`; a single variable
grotesk used for display **and** body — display at 62–70px / weight 700 / uppercase /
line-height ≈1.0 with per-letter span splitting for staggered reveals; manifesto prose
at ~43px; Tronica Mono 16px uppercase for nav/labels/status chrome (`Work`,
`THEME[A]`, `SOUND[-]`, `Haoqi (c) 2026`, coordinates); a blinking terminal caret;
**zero border-radius anywhere**; semantic accent colors wired to meaning via CSS
variables; motion that respects `prefers-reduced-motion`.

Adapted tokens for SchemeGPT:

- **Palette:** paper `#FBFAF4` (background), ink `#000000` (text), paper-dim
  `#EFEDE7` (secondary surfaces/rules). Semantic accents (never decorative):
  verified green `#00784A` (verified schemes, success), seed gold `#8A6A00` /
  `#EBC669` (directory seeds, cautions), signal red `#C0434C` (errors, out-of-domain
  notices), acid green `#C0FE04` (live-mode signal, used only on black inversions),
  link blue `#0077BC` (official external sources). White-on-black inversion blocks
  for the footer and source panels.
- **Typography:** **Archivo** (variable grotesk, OFL) for display and body — the
  haoqi.role of one-family sans, chosen instead of TikTok Sans which is not openly
  licensed. Display: uppercase, weight 700–800, line-height 1.0, fluid clamp up to
  ~70px; hero letters wrapped in spans for staggered reveal. Body/UI: Archivo 400/500.
  **Martian Mono** (OFL) 16px uppercase for the terminal chrome: nav, status labels,
  stamps, coordinates, footer. Hindi/Devanagari falls back to Noto Sans Devanagari;
  layouts tolerate ~30% longer Hindi strings.
- **Terminal chrome as signature:** nav and status rendered as bracketed mono
  switches — `SCHEMES[36]`, `MODE[LIVE]`/`MODE[DEMO]`, `LANG[EN]`/`LANG[HI]`, footer
  `SCHEMEGPT (C) 2026 · 28.6139 N X 77.2090 E` (Delhi). The chat input carries a
  blinking block caret (CSS `caret-blink`, disabled under reduced motion) and the
  streaming answer ends in a caret that disappears on `done`.
- **Structure:** zero border-radius everywhere; 1px ink rules; generous full-bleed
  section padding (haoqi uses `py-18 lg:py-24` rhythm); flat surfaces, no shadows.
- **Honesty as visual language:** `VERIFIED · <date>` and `DIRECTORY SEED` as
  mono-uppercase stamps (green/gold); demo answers get a distinct treatment (black
  inversion header strip + `MODE[DEMO]`) so live and demo are never confused;
  sources are ruled cards citing file and `data_status`; exact policy quotes render
  as indented blockquotes inside a hairline left rule.
- **Motion:** one orchestrated moment — hero headline per-letter staggered reveal on
  load; elsewhere only functional motion (caret blink, message fade-in, streaming
  text). All animation gated behind `prefers-reduced-motion`.
- **Accessibility:** WCAG AA contrast on all token combinations (acid green is used
  only as text on black or as non-text highlights), keyboard-navigable chat and
  forms, visible focus, semantic headings.

## Error handling

- API unreachable/timeouts in `web`: friendly inline error with retry; never a blank
  screen. Server-rendered pages degrade to an explanatory page if the API is down.
- SSE failures mid-stream: partial answer preserved, labelled failure notice appended,
  stream closed cleanly; client stop button aborts without error styling.
- Profile/validation 422s: field-level messages next to the offending input.
- Out-of-domain questions and all honesty boundaries: behaviour identical to today.

## Testing and verification strategy

- **Every slice:** `next build` clean, existing smoke checks still pass
  (`py_compile`, `scripts/validate_data.py`, `docker compose config --quiet`,
  `/health`, `/coverage`), plus tests for the slice's own surface. The pytest suite is
  introduced incrementally from Slice 1 and reaches the full list in Slice 4
  (validation bounds, profile token flow, recommendation determinism, `/schemes`
  contract, stream event sequence, demo-fallback labelling).
- **Frontend behaviour:** manual/browser-based verification per slice (chat streaming
  in live+demo, filters, profile flows, en/hi) using the available browser tooling.
- **Retrieval changes:** RAGAS before/after with dated report updates; no score is
  ever fabricated or estimated.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Next.js adds Node runtime + RAM on a small VPS | Node service is ~150–200 MB; the ≥2 GB guidance already covers it; document in runbook |
| SSE through Groq rate limits | Existing fallback semantics: rate-limit → labelled demo stream, never a raw error |
| Retrieval "upgrade" regresses faithfulness | Measurement gate in Slice 4; adopt only on net improvement |
| Scope creep into auth/corpus | Non-goals section above; each slice has an explicit done-when |
| Two UIs drift during migration | Streamlit is frozen (bug fixes only) from Slice 1 until removal in Slice 5 |
