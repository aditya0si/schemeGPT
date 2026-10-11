# 03 Security packet

Reader: the customer's IT security and data-protection staff. Scope: the single-tenant pilot install
described in `02-pilot-scope.md` (Docker Compose on one customer host). Everything tagged
"measured (from this repository)" was read out of the code or the recorded documentation; everything
else is stated as assumption (yours to change) or as an open item. No customer environment described
here has been inspected; the pilot install is the first look at it.

## 1. Data flow

```
citizen or agent
   |  question (2-2000 chars), optional language, optional profile payload
   v
Next.js web (port 3000) or helpdesk client
   |  server-side proxy; the API is bound to 127.0.0.1:8000 on the host
   v
FastAPI service  ----------------------------------------------------------.
   |  1. optional question normalization (model call, question text only)   |
   |  2. local retrieval: embeddings run in-process, no network call        |
   |     (multilingual-e5-small, model baked into the image)                |
   |  3. PostgreSQL + pgvector over the internal Compose network            |
   |     (not published to the host, plaintext inside the docker network)   |
   |  4. generation: question + retrieved excerpts + optional profile block |
   |     are sent to the model provider over HTTPS                          |
   '------------------------------------------------------------------------'
   |
   v
answer + cited sources + machine-verified quotes
```

Stores written by the service: `user_profiles` and `query_cache` tables in the customer's own
PostgreSQL, `data/feedback.jsonl` on the host, `var/ops_state.json` on the mounted volume.

## 2. What leaves the customer network, and what never does

| Leaves the customer network, per query | Detail |
| --- | --- |
| The question text | as typed, and once more as a normalized rewrite when the normalization call runs |
| Retrieved policy excerpts | verbatim corpus text (public scheme material) that retrieval selected |
| The system prompt | fixed instruction text shipped in the image |
| The profile block, only when the request attaches a profile | see the correction in section 3 |
| Traffic metadata | TLS connection metadata to the provider (source IP of the customer's egress) |

| Never leaves the customer network (measured) | Why it cannot |
| --- | --- |
| Profile access tokens and their hashes | tokens are accepted by header on the profile endpoints only; no outbound code path has access to them |
| Profile ids, admin tokens | not part of any provider payload; operator status output masks provider URLs and strips credentials |
| The corpus and the vector store | embedding and retrieval are local (`intfloat/multilingual-e5-small`, 384-d, in-process) |
| Feedback records, saved profiles as stored | they are written to the local database and the local feedback file; not read into provider calls |
| Application logs | logs hold exception types and operator actions, not question or profile text: no log call in `app/` references question, profile or payload text (measured by inspection) |
| Metrics | `GET /metrics` returns in-process counters and latency percentiles only, no per-request text |

## 3. Correction you should read carefully

An earlier internal brief claimed that no profile data is ever sent to the model provider. That is
not what this code does. `app/rag.py` renders a delimited profile block into the prompt
(`HUMAN_TEMPLATE = "Context:\n{context}\n\n{profile_context}\n\nQuestion: {input}"`, built by
`_build_profile_context`). So:

- request with no profile: question + retrieved excerpts only. This is the pilot default.
- request with a profile attached: the profile fields the caller supplied also go to the provider.

Mitigation that the pilot will use: profile collection is disabled by policy (clients never send a
`profile` field), so the profile store is out of the data flow. If the customer later wants profiles,
the profile fields are bounded (`ProfileData`: display name up to 100 chars, state, age, income,
occupation, social category, gender, rural, disability, family size, up to 20 goals, whole serialized
payload capped at 12,000 chars, measured in `app/schemas.py`) and `display_name` should be left blank
or pseudonymous because it is free text and is the field most likely to carry a real name. Any
deployment that enables profiles should also decide whether the provider is allowed to see them.

## 4. Where data lives

| Store | Contents | Location | Retention (measured unless stated) |
| --- | --- | --- | --- |
| `user_profiles` (PostgreSQL) | profile JSONB, SHA-256 hash of the access token, timestamps | customer host, private docker network | no automatic expiry exists; deletion is explicit via `DELETE /profiles/{id}` with the token |
| `query_cache` (PostgreSQL, semantic cache) | question text, language, 32-character SHA-256 prefix of the profile payload, embedding, cached answer | customer host | 7-day TTL, 2,000-entry cap, served only at cosine >= 0.95; disable with `ENABLE_SEMANTIC_CACHE=false` |
| `data/feedback.jsonl` | question, answer, rating, language, optional comment, timestamp | customer host, git-ignored file | append-only, no retention policy or purge implemented (gap) |
| Operator audit | last 50 entries: timestamp, action, actor label, reason | process memory | lost on restart by design (bounded to avoid an in-process leak) |
| `var/ops_state.json` | kill-switch state and the free-text reason string | mounted volume | persists until changed; the reason string can contain a person's name, so treat the file as sensitive |
| PostgreSQL corpus and vectors | public scheme records and embeddings | customer host, `pgdata` volume | project lifetime |
| Upgrade backups | `pg_dump` SQL files written by `deploy/field/upgrade.sh` | `deploy/field/backups/` on the host | not managed by the app; the customer owns their deletion and their file permissions (gap) |

## 5. Profile token model

`POST /profiles` returns `access_token` exactly once, in that response only. What is stored is
`hashlib.sha256(raw_token)` in the `token_hash` column, compared with `secrets.compare_digest`
(measured in `app/profiles.py`). Read, update and delete require the token in the `X-Profile-Token`
header; a wrong token and a missing profile both return 404 so the endpoint does not confirm which
ids exist. The raw token is never logged and never returned again. Loss of the token means loss of
the profile; in the pilot that is the intended behaviour.

## 6. Access control and secrets in this deployment

| Surface | Control (measured) |
| --- | --- |
| Operator endpoints (`/ops/ai`, `/ops/provider`, `/ops/audit`) and `POST /ingest` | shared `ADMIN_TOKEN` in the `X-Admin-Token` header, constant-time comparison; if the variable is blank the endpoints return 503 rather than running unauthenticated |
| Read-only operator status (`GET /ops/status`) | intentionally public: states, counters and a masked endpoint only, provider exception types but never provider error text |
| Citizen endpoints | no authentication by design; a per-IP token bucket (default 20 requests per minute) protects the shared provider quota |
| Model provider key | `GROQ_API_KEY` in the customer's `.env` on their host; if the customer issues the key, revocation stays with them |
| Provider endpoint | `POST /ops/provider` is in-memory only; the durable form is `GROQ_API_BASE` in the environment, so nobody with API access alone can permanently repoint traffic |
| Database | not published to the host; the Compose network is the boundary; the default development password must be changed for the pilot |

## 7. Audit trail contents

Each operator action appends one entry with `at` (UTC timestamp), `action`
(`ai_disabled`, `ai_enabled`, `provider_endpoint_set`, `provider_endpoint_cleared`), `actor` (free
text, up to 64 characters) and `reason` (free text, up to 200 characters). Read it with
`GET /ops/audit` and the admin token. Limits, stated plainly: at most 50 entries, held in memory
only, no export to a SIEM, not tamper-evident, and `actor` is a label an operator types, not an
authenticated identity.

## 8. Sub-processors and third parties

| Party | Role | Data it receives | Note |
| --- | --- | --- | --- |
| Groq (model provider) | generation and question normalization over HTTPS | question text, retrieved excerpts, optional profile block | default is the free tier: no contractual data-residency or retention commitment is asserted by us. Decide between their gateway via `POST /ops/provider`, a paid tier, or retrieval-only operation |
| Container registry | image pulls during install and upgrade | none beyond normal registry metadata | blocked in an air-gap install; images arrive in the signed bundle |
| Hugging Face | embedding model download | none | the model is baked into the API image (`intfloat/multilingual-e5-small`, about 470 MB), so this is a build-time concern |
| LangSmith (optional tracing) | chain traces | prompts and answers | env-only (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`); off by default. It must stay off for this engagement unless the customer gives written approval |
| Hosted demo topology (Vercel, Fly.io, Neon) | alternative deployment path documented in `docs/DEPLOY.md` | would move the database and API off-premise | not the pilot topology. If the customer ever wants it, that is a separate security review |

## 9. Controls that are NOT in place

Said without qualification, because a security reviewer will find each of these in the first hour:

- No SOC 2 report, no ISO 27001 certificate, no certification in progress.
- No third-party penetration test has been performed on this system.
- No SSO, no per-user identity, no RBAC on the operator plane: one shared admin token, and the audit
  `actor` field is free text.
- No automated retention or erasure job for profiles or feedback; no data-subject export endpoint
  for profiles beyond reading a profile back with its token.
- No consent capture or consent records in this codebase.
- PII redaction covers the `/query` question and the `/query/stream` token
  stream. Detected identifiers are replaced with request-scoped placeholders
  before the provider call and restored in the answer; PII-bearing requests
  bypass the semantic cache. The streaming path adds a bounded overlap buffer so
  an identifier split across SSE chunks is still redacted, and the held tail is
  discarded on error or disconnect. Free-text profile fields, the `sources` and
  `quotes` event payloads, and every other field are NOT yet covered, and no
  real-network egress audit has been performed (the streaming guarantee is
  proven against a stubbed provider). The only other bounds remain length caps
  (question 2 to 2000 characters, profile payload 12,000 characters).
- No encryption applied by the application at rest; the API to database connection inside the
  Compose network is plaintext. Host-level disk encryption is the customer's control.
- No TLS termination in the app: it expects to sit behind the customer's reverse proxy, which the
  pilot must configure.
- No SIEM integration and no metrics push; `GET /metrics` is pull-only.
- No high availability: one host, one API container, and a short downtime window on upgrade.
- No formal incident-response process in the product beyond the kill switch, the audit trail and the
  rollback script; breach notification would follow the customer's own process.
- No DR plan beyond the upgrade snapshot and the rollback script; verify the restore path before
  relying on it.
- The failure drill harness exists and is scripted, but the recorded run in
  `docs/evidence/FIELD-DRILL.md` completed phase A and exited 127 on phase B, so a clean
  end-to-end rehearsal pass is not on record.
- Corpus accuracy, not confidentiality, is the live data risk: a large share of records are
  automated imports and directory seeds, and no record carries a verified eligibility decision
  unless it is `sample_verified`.

## 10. DPDP-relevant controls that exist in a sibling project, not here

A separate project (an insurance claims system, different repository) implements consent records with
granular categories and a withdrawal path, a structured data export, erasure with a 30-day grace
period and anonymization of the profile row, weekly data-minimisation jobs, and a named grievance
officer. Those are real, working controls in that codebase. They are **not implemented in
SchemeGPT**, and this document does not claim them. Read them as a reference design.

For the pilot, the cheaper and more honest path is to avoid the obligation: do not collect identity
data, run without profiles, and delete the specific rows or files on request. If the department needs
consent artefacts, withdrawal and erasure semantics for this system, that is a scoped piece of work
with its own review, and it should be estimated before any citizen-facing rollout, not during it.

## 11. Questions their security team will ask, and the answers

| Question | Answer |
| --- | --- |
| SOC 2 status? | None. No report exists. |
| Penetration test? | None. No third-party test has been performed. |
| Where is inference performed? | At a third-party provider, outside India, by default. Options: their gateway via `POST /ops/provider`, a paid tier with a contract, or retrieval-only mode with generation switched off. |
| Does the system answer Aadhaar or identity data questions? | No. No identity verification, no beneficiary-database lookup, no eligibility decisions. |
| Can we see every byte leaving? | Yes. Point `POST /ops/provider` at their proxy, or at `deploy/field/stub_provider.py`, and capture the payload. Criterion AC-11 in the pilot relies on exactly this. |
| Are queries retained? | Only with the feedback endpoint (append-only file) or the semantic cache (7-day TTL). Both are local. The cache can be switched off. |
| Can we switch it off without taking the service down? | Yes. `POST /ops/ai` with `enabled: false` stops generation, serves retrieval-only answers assembled from verbatim excerpts, keeps `GET /health` at 200, and survives a restart. |
| Who holds the admin token? | The customer's IT should hold it; we ask them to generate it. |
| What is your breach process? | There is no product-level process. Use the customer's, plus the kill switch and the audit trail; expect the audit trail to hold at most 50 in-memory entries and to be lost on restart. |
| Do you process data on our behalf under a contract? | Not in the pilot. There is no DPA in this pack; the pilot runs on their host with their keys, and their approval of this packet is the written record we ask for. |

## 12. What we need from the customer's security side

1. A decision on provider egress: allowed through the proxy, routed via their gateway, or fully
   air-gapped with retrieval-only operation.
2. Their internal CA installed on the host if the proxy inspects TLS. We will not disable
   certificate verification, and a `PF-045` finding is not a warning to be waved through.
3. A signed note accepting or amending section 9, so the residual risk is a documented decision
   rather than an assumption.
4. A retention decision for `feedback.jsonl`, profile rows, and the `deploy/field/backups/` SQL
   files.
5. Confirmation of who holds `ADMIN_TOKEN`, and the on-call rota that can use it.
6. Confirmation that the pilot runs without profiles, or written approval for profile fields
   reaching the provider.
