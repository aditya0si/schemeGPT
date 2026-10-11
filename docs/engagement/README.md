# SchemeGPT engagement pack

Forward-deployed engineering artifacts for a deployment of SchemeGPT (bilingual English/Hindi
retrieval-augmented decision support over Indian government scheme records) into a state
government welfare-scheme helpdesk. This pack is written to be handed to a customer's IT and
programme staff. It is not marketing material.

## Order of use

1. `01-discovery.md` - run the discovery call, quantify the baseline.
2. `02-pilot-scope.md` - agree the four-week pilot, its acceptance criteria and the go/no-go rule.
3. `03-security-packet.md` - give this to their security and data-protection staff early. It is the
   document most likely to stop a pilot, so it should go out before week 1.
4. `04-roi-model.md` - the arithmetic, with every input exposed so finance can argue with it.
5. `05-handoff-and-rollout.md` - enablement, change management, escalation, and the handover to
   the customer's own team.
6. `06-ops-one-pager.md` - the printed page that sits with the on-call operator from day one.

## Labelling rule

Every input in this pack carries one of these labels. Nothing carries none.

| Label | Meaning | What to do with it |
| --- | --- | --- |
| measured (from this repository) | taken from the code, tests, docs or a recorded run in this repository | quote as is; if it changes, update this pack |
| assumption (yours to change) | a number or claim inserted to make the arithmetic run | replace with the customer's own number before any decision |
| illustrative example | a fabricated customer used to show a filled-in artifact | never presented as a real reference |

No customer name, logo, contract value, or performance metric attributed to a real organisation
appears anywhere in this pack. Where a proposal is neither measured nor an assumption (scope,
criteria, sequence), it is a proposal: the customer is expected to edit it.

## Files

| File | What it is for | Primary reader |
| --- | --- | --- |
| `README.md` | index, labelling rule, the measured facts every other artifact relies on | all |
| `01-discovery.md` | discovery call template plus one filled exemplar with a quantified baseline model | field engineer, programme lead |
| `02-pilot-scope.md` | four-week pilot: in/out of scope, weekly deliverables, testable acceptance criteria, prerequisites, explicit go/no-go rule | programme lead, IT, helpdesk manager |
| `03-security-packet.md` | data flow, what leaves the network and what never does, retention, PII, sub-processors, and controls not yet in place | IT security, data-protection officer |
| `04-roi-model.md` | transparent cost/benefit arithmetic with low/expected/high inputs and a worked case | programme lead, finance |
| `05-handoff-and-rollout.md` | training, change management, escalation path, handover to the customer's team | helpdesk manager, IT operations |
| `06-ops-one-pager.md` | on-call page: operator endpoints, exact curl commands, escalation ladder | on-call operator |

## Standing facts (measured (from this repository))

| Fact | Value | Where it comes from |
| --- | --- | --- |
| Corpus size | 2,105 Markdown records: 2,063 imported scheme records (`data/myscheme/`), 36 state/UT directory seeds (`data/states/`), 6 hand-verified central samples (`data/schemes/`) | file counts under `data/`; `docs/data-operations.md` |
| Full-corpus index size | about 20,000 chunks, 26,395 vectors (project build record, not re-derived in this pack) | project record for the full-corpus re-embed |
| Provenance field | every record carries `data_status`: `sample_verified` (hand-checked), `directory_seed` (national portal discovery entry), `myscheme_import` (automated import from a published dataset) | `app/ingest.py`, `docs/data-operations.md` |
| Retrieval | three channels fused with Reciprocal Rank Fusion: dense embeddings (multilingual-e5-small, 384-d), PostgreSQL full-text (`tsvector`), lexical scheme-name channel | `app/retrieval.py`, `docs/AI-ENGINEERING.md` |
| Citation checking | every quoted line is verified by exact normalised substring containment against the retrieved text; a failed quote is shown as unverified, never silently repaired | `app/quotes.py` |
| Retrieval quality gate | Hit@4 0.875, MRR@4 0.796875 over 16 English/Hindi/Hinglish/profile cases on the full corpus; CI floors Hit@4 >= 0.85 and MRR@4 >= 0.60. The lexical tie-breaking used to be plan-dependent (0.8125 vs 0.875) and is now deterministic; the deterministic 0.8125 exposed a duplicate-scheme diversity defect, fixed by capping one chunk per logical document and preferring the higher-trust (hand-verified) copy by `data_status` — a correctness rule, not score tuning (project build record, not re-derived in this pack) | project retrieval CI gate |
| Test suite | CI runs `python -m pytest -q` with no database, no Groq call, no model download; the project reports 120 tests (117 top-level test functions counted in `tests/`) | `.github/workflows/ci.yml`, `tests/` |
| Serving-layer load test | 25 concurrent users, 860 streamed requests, 0 failures, 14.5 streams/s, p95 25 ms, in demo mode (no LLM call) | `loadtest/RESULTS.md` |
| Operator control plane | AI kill switch (durable across restart), provider circuit breaker (3 consecutive failures, 30 s cooldown, one probe, in-memory), runtime provider endpoint override (in-memory) | `app/ops.py`, `docs/FIELD-DEPLOY.md` |
| Default public rate limit | 20 requests per minute per IP (`RATE_LIMIT_RPM`) | `app/config.py` |
| Semantic cache | pgvector-backed, cosine >= 0.95, 7-day TTL, 2,000-entry cap, keyed by language and a 32-character SHA-256 prefix of the profile payload | `app/semantic_cache.py` |
| Deployment kit | Docker Compose (db + api, optional web/streamlit); air-gap bundle with checksums and optional detached signature; host preflight with PF-0xx codes; upgrade with database and environment snapshot plus automatic rollback on a failed health gate; scripted failure drill | `docs/FIELD-DEPLOY.md`, `deploy/field/` |
| Drill evidence state | a drill run is recorded at `docs/evidence/FIELD-DRILL.md`; phase A completed, phase B exited 127. A clean end-to-end rehearsal pass is not yet on record | `docs/evidence/FIELD-DRILL.md` |

## Limits to state in the first meeting, every time

- Answers are grounded only in the ingested corpus. If a scheme is not in the corpus the system
  says so. It is not an eligibility authority and not legal advice.
- A large share of the corpus is unverified (`directory_seed` and `myscheme_import` records).
  `GET /coverage` reports the split and must be shown to any customer-facing user.
- The shipped provider default is Groq's free tier, 8k tokens per minute, which bounds throughput
  per instance.
- Single-host Compose is not high availability. An upgrade recreates the API container, so there
  is a short downtime window.
- The kill switch and the circuit breaker are per-instance controls, not fleet controls.
- There is no production multi-tenant deployment yet. The pilot is a single-tenant install on the
  customer's own host.
