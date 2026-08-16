# Data operations for SchemeGPT

This document describes how verified scheme records are sourced, written,
catalogued, validated, and re-ingested. It exists so the corpus stays an
honest, repeatable dataset: **the current corpus is a nationwide directory seed
plus six central sample records, not all government schemes.**

## What the corpus currently is

- `data/india_states.json` — 36 jurisdictions (28 states + 8 Union
  Territories). Every record is a `directory_seed`: it maps the jurisdiction
  and links to the official national MyScheme discovery portal.
- `data/states/*.md` — one Markdown directory entry per jurisdiction. These are
  discovery/coverage seeds (`data_status: directory_seed`), never verified
  eligibility decisions.
- `data/schemes/*.md` — the verified central sample records. Today exactly six:
  PM-KISAN, Ayushman Bharat PM-JAY, PMAY-G, PM-SYM, Startup India, and GST.
  Each has `data_status: sample_verified`.
- `data/scheme_catalog.json` — the structured catalog used by
  `/recommendations` and by ingestion for chunk metadata. It mirrors the
  Markdown corpus (6 central records + 36 directory seeds).
- `docs/scheme-record-template.md` — the template for adding a new verified
  scheme record. It lives outside `data/` so it is never ingested.

There is **no claim that all government schemes have been ingested**. Coverage
transparency is exposed by `GET /coverage` (and `app/catalog.coverage_summary`).

## Authoritative sources to prefer

Use the **official** source for every fact:

1. Official scheme pages on **ministry / department portals** (e.g.
   `pmkisan.gov.in`, `pmjay.gov.in`, `gst.gov.in`).
2. The official national **MyScheme discovery portal** (`https://www.myscheme.gov.in/`)
   for scheme presence, categories, and the latest status.
3. Gazette notifications, scheme guidelines PDFs, and press releases hosted on
   the issuing department's domain.

Prefer `https://` URLs only. Record the exact URL used, in the record's
`source_url` field and inside the Markdown document.

## One Markdown file per verified scheme

Create one file `data/schemes/<stable-slug>.md` per verified scheme, using
`docs/scheme-record-template.md`. Each file must contain:

- the scheme name and one concise scope paragraph;
- a `## Source` section with the exact official `source_url`;
- `## Eligibility`, `## Exclusions`, `## Benefits`, `## Documents`, and
  `## How to apply` sections;
- a `## Not official advice` boundary;
- front-matter-equivalent metadata as the template specifies (jurisdiction,
  `last_verified`, `data_status`).

Facts are copied from the official source **only** when the source's terms
allow it and its `robots.txt`/crawling policy is respected. When a required
fact is missing from the official source, **write "not specified in the
official source" rather than fabricating eligibility**.

## Matching catalog entry and stable ids

Every Markdown file must have a matching entry in `data/scheme_catalog.json`:

```json
{
  "id": "<stable id, e.g. pm-kisan or state-ap>",
  "name": "Official scheme name",
  "jurisdiction": "central",
  "source_file": "data/schemes/<stable-slug>.md",
  "tags": ["<catalog tags that match the recommender goals>"],
  "data_status": "sample_verified",
  "last_verified": "YYYY-MM-DD",
  "source_url": "https://..."
}
```

Rules:

- `id` is stable forever: changing it orphans saved recommendations and
  evaluation references.
- `source_file` is the project-root-relative path and must exactly match the
  file on disk.
- `jurisdiction` is `"central"` for central schemes, or the state/UT name for
  jurisdiction-level records.
- `data_status` is **`sample_verified`** for the six existing central sample
  docs, **`directory_seed`** for state/UT entries, and one of those two values
  everywhere else. Do not introduce new values without updating
  `scripts/validate_data.py` and this document.
- `last_verified` is the date the facts were checked against the official
  source.

## Validate

Dependency-free validator (Python stdlib only):

```bash
python scripts/validate_data.py
```

It checks, and exits non-zero with explained errors on failure:

- exactly 36 unique states/UTs (28 states + 8 UTs);
- every state Markdown file and catalog entry exists;
- every catalog `source_file` exists on disk;
- `data_status` is one of the allowed values;
- official/source URLs are `https`;
- no duplicate catalog ids or source files;
- every `*.json` file in `data/` and `eval/` parses.

On success it prints a compact summary. Run it from the project root (or any
directory — paths are resolved relative to the script location).

## Re-ingest

- Startup auto-ingestion is unchanged: on API start, if the vector store is
  empty, `app/ingest.ingest()` ingests `data/schemes/*.md` and
  `data/states/*.md` idempotently (content-hash chunk ids; existing vectors are
  never deleted).
- Manual re-ingest: `POST /ingest` with the `X-Admin-Token` header equal to
  `ADMIN_TOKEN`. If `ADMIN_TOKEN` is blank the endpoint returns 503
  (disabled) — a public unauthenticated re-ingest endpoint is not acceptable.
- Idempotency: re-runs skip unchanged chunks and refresh catalog metadata in
  place; they never delete vectors.

## Never

- Scrape or copy content without respecting the source's terms and
  `robots.txt`.
- Fabricate missing eligibility, benefit amounts, or deadlines.
- Present a `directory_seed` record as a verified eligibility decision.
- Introduce new `data_status` values silently.
