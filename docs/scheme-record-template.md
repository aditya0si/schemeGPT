# Scheme record template

Use this template for every **verified** scheme record added to `data/schemes/`.
It lives in `docs/` — **outside** `data/` — so it is never ingested by the
vector store. Copy it, fill every section from the official source, then add the
matching `data/scheme_catalog.json` entry.

```markdown
# <Official scheme name>

One concise paragraph: what the scheme is, who it targets, and its flagship
benefit. Write only facts that appear in the official source below.

## Source

- **Official source:** <exact https URL on the ministry/state/MyScheme portal>
- **Checked on:** YYYY-MM-DD
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** central   <-- or the state/UT name for a jurisdiction-level scheme

## Eligibility

- <bullet list of eligibility conditions, verbatim from the official source>
- If the official source does not state a condition, write "not specified in
  the official source". Never fabricate eligibility.

## Exclusions

- <bullet list of excluded groups, verbatim from the official source>

## Benefits

- <bullet list of benefit amounts / coverage / frequency, verbatim from the
  official source>

## Documents required

- <bullet list of documents, verbatim from the official source>

## How to apply

1. <step-by-step application steps, verbatim from the official source>
2. <include the official portal / application URL>

## Not official advice

This record is a **sample_verified** entry: facts were checked against the
official source on the "Checked on" date, but government schemes change.
SchemeGPT is a discovery assistant, not an official eligibility decision.
Before applying, re-verify eligibility, exclusions, and documents on the
official source above.
```

## Matching catalog entry

Add the matching entry to `data/scheme_catalog.json` (inside the `records`
list). The `id` and `source_file` must be stable — do not change them later.

```json
{
  "id": "<stable id, e.g. pm-kisan>",
  "name": "<official scheme name>",
  "jurisdiction": "central",
  "source_file": "data/schemes/<stable-slug>.md",
  "tags": [
    "<one or more recommender tags, e.g. health, income support>"
  ],
  "data_status": "sample_verified",
  "last_verified": "YYYY-MM-DD",
  "source_url": "https://<official source URL>"
}
```

Rules:

- `source_file` must exactly match the file you created and the `## Source`
  URL must be `https://`.
- `data_status` is `sample_verified` for verified sample records and
  `directory_seed` for state/UT discovery entries. Never invent a third value.
- `last_verified` must equal the "Checked on" date in the Markdown file.

## Validate and re-ingest

1. `python scripts/validate_data.py` — must pass (stdout summary, exit 0).
2. Re-ingest: `POST /ingest` with the `X-Admin-Token` header equal to
   `ADMIN_TOKEN` (or restart the API; startup auto-ingestion is idempotent).

See `docs/data-operations.md` for the full workflow, sourcing rules, and
"never scrape / never fabricate" boundary.
