# 02 Pilot scope (four weeks)

Objective: prove, on the customer's own host and their own queries, that grounded retrieval with
verified citations reduces helpdesk handling time without producing an answer the department cannot
defend. Four weeks, single tenant, no change to the customer's existing helpdesk systems.

Labelling, for this document as a whole: product facts carry the tag measured (from this repository);
every threshold, host specification, duration, prerequisite and threshold value below is
assumption (yours to change) and is expected to be amended by the customer before the pilot starts.

## 1. In scope

| In scope | Concrete form |
| --- | --- |
| One single-tenant install on the customer's host | Docker Compose (`db` + `api`, plus `web` if they want a browser UI) on one VM; the API binds to `127.0.0.1:8000` only |
| Grounded question answering with citations | `POST /query` and `POST /query/stream` (English and Hindi, including Hinglish input) |
| Deterministic starter recommendations | `POST /recommendations` (no model call, catalog-driven) |
| Corpus scoped to agreed schemes | the 6 hand-verified central sample records plus a named set of schemes the customer verifies during the pilot, plus the existing 36 state/UT directory seeds with their `data_status` shown |
| Operator controls, exercised in front of the customer | `POST /ops/ai`, `POST /ops/provider`, `GET /ops/status`, `GET /ops/audit`, `GET /metrics` |
| Field deployment kit | preflight (`deploy/field/preflight.py`), bundle verification, install, upgrade with snapshot and auto-rollback, scripted drill (`deploy/field/drill.py`) |
| Measurement | retrieval gate on 200 customer queries, SME usability scoring on 200 answers, ticketed handling-time comparison, containment flag |

## 2. Out of scope (say this out loud in the kickoff)

- Eligibility determination or any "you qualify" statement. The helpdesk explains published criteria
  and points to the official source.
- Citizen identity, Aadhaar, DBT or beneficiary-database integration. No citizen login.
- Telephony / IVR / WhatsApp integration, and any change to the helpdesk CRM.
- Multi-tenant, multi-instance, fleet-wide controls, or high availability. The kill switch and the
  circuit breaker are per-instance controls (measured limitation, `docs/FIELD-DEPLOY.md` section 7).
- Zero-downtime upgrades. Upgrading recreates the API container, so there is a short downtime window.
- A paid model tier or a second provider unless the customer signs a written addendum. The shipped
  default is a free-tier provider at 8k tokens per minute, which caps throughput per instance.
- Bulk ingestion of the customer's own circular PDFs beyond the named scheme set. PDF extraction
  quality is the customer's risk to accept if they want it.
- Any statement that the corpus is exhaustive. A large share of the corpus is unverified import and
  directory records (`myscheme_import`, `directory_seed`), reported by `GET /coverage`.
- Procurement, DPIA sign-off, or security certification. We provide the material; their processes run
  on their timeline.

## 3. Deliverables by week

| Week | Deliverable | Done when |
| --- | --- | --- |
| 1 | Install on the customer host, with a preflight JSON record | `deploy/field/reports/preflight-<site>.json` exists, preflight exit code 0 (or 2 with each warning accepted in writing), `GET /health` returns `status: ok` |
| 1 | Corpus scope freeze: the named scheme list to be hand-verified, with the verifying officer named | written list, signed by the programme owner |
| 1 | Pilot kit: question runner (20-question bilingual set), independent quote re-checker, retrieval gate pointed at the pilot query set | scripts run end to end on the installed host and write a JSON result file |
| 1 | Baseline timing measurement | 5 agents timed on the same 20 questions using today's process, result recorded |
| 1 | Security packet walkthrough with the data-protection contact | questions from `03-security-packet.md` section 11 answered in writing or listed as open |
| 2 | Shadow mode: agents use the system on live queries with SME review | at least 300 answered queries in the log, review coverage documented per day |
| 2 | Daily triage of refusals, degraded answers and failed quotes | 10 working days of triage notes, each entry with a cause code |
| 3 | One citizen-facing channel live in a limited setting (2 districts or one topic group) with a disclosure line | 100 citizen-facing answers logged, each with its source citation and review status |
| 3 | Kill-switch and provider-outage drills run during business hours | both drills recorded with timestamps and observed states |
| 3 | Customer on-call rota active, vendor as backup | named on-call person per day, escalation ladder from `06-ops-one-pager.md` agreed |
| 4 | Measurement analysis | AC-13 and AC-14 computed on the full sample from raw logs, with the raw logs handed over |
| 4 | Upgrade and rollback rehearsal | `deploy/field/logs/` contains an upgrade record and a rollback record; vector-store row count equal before and after |
| 4 | Handover walkthrough | customer operators run the drills themselves while the vendor watches and does not touch the keyboard |
| 4 | Final report and decision meeting | per-criterion pass/fail with measured values, failed items listed, recommendation recorded |

## 4. Acceptance criteria

Every criterion names the test. P0 must all pass. P1 are reported and argued, not gates. Numeric
thresholds here are assumption (yours to change); the repository's own gate floors are tagged
measured (from this repository).

| ID | Criterion | Test (exact) | Class |
| --- | --- | --- | --- |
| AC-01 | Install is healthy and preflight is clean | `python3 deploy/field/preflight.py --label <site> --json deploy/field/reports/preflight-<site>.json` then `curl -s $API/health` | P0 |
| AC-02 | 20 bilingual questions return grounded answers | for each of 10 English and 10 Hindi/Hinglish questions: `curl -s -X POST $API/query -H 'Content-Type: application/json' -d '{"question": "...", "language": "hi"}'`; require HTTP 200, `mode` in `live` or `degraded`, and at least 1 entry in `sources` | P0 |
| AC-03 | Stream protocol order and completion | `curl -sN -X POST $API/query/stream -H 'Content-Type: application/json' -d '{"question": "..."}'`; require `sources` before the first `token`, and a terminal `done` for at least 19 of 20 streams in one run | P0 |
| AC-04 | No fabricated citation presented as verified | independently re-check every quoted line against the retrieved source text (normalised substring containment); require zero entries where the answer claims a verified quote that is not contained in the source | P0 |
| AC-05 | Retrieval gate on the customer's own 200 queries | run the repository's retrieval gate harness over the pilot query set; require Hit@4 >= 0.80 and MRR@4 >= 0.60. The CI floors used on the repository's own 16-case set are Hit@4 >= 0.85 and MRR@4 >= 0.60 (measured). Pointing the harness at a customer query file is a week-1 deliverable, and this criterion cannot pass until that exists | P1 |
| AC-06 | Kill switch works, survives a restart, and does not look like an outage | `curl -s -X POST $API/ops/ai -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"enabled": false, "reason": "pilot drill", "actor": "oncall"}'`; then `POST /query` must return `mode: degraded` with sources, `GET /health` must still return HTTP 200 with `ai: "disabled"`; after `docker compose restart api` the state must persist; re-enabling must restore `mode: live` | P0 |
| AC-07 | Circuit breaker contains a provider outage | point the client at `deploy/field/stub_provider.py` configured to fail, issue calls, and record `GET /ops/status`: `breaker.state` must reach `open` after 3 consecutive failures, reject during the cooldown, then close after exactly one successful probe | P1 |
| AC-08 | Traffic can be routed through the customer's gateway at runtime | `POST /ops/provider` with the customer gateway base URL, then `GET /ops/status` must show `provider.endpoint` as scheme + host + path with any credentials and query string removed; sending `{"base_url": ""}` must return to the configured endpoint | P1 |
| AC-09 | Failures degrade honestly | during the outage window, 10 questions must return `mode` `degraded` or `demo` with a notice, and the run must contain zero HTTP 5xx responses and zero stack traces in the response body | P0 |
| AC-10 | Upgrade and rollback are rehearsed, not asserted | `bash deploy/field/upgrade.sh --to-version <next>` then `bash deploy/field/rollback.sh`; require both records in `deploy/field/logs/`, the health gate to have run, and the vector-store row count to be unchanged across the upgrade. If the customer's change freeze blocks this, a signed waiver downgrades it to P1 and it is the first task after the pilot | P1 |
| AC-11 | No identifiers on the wire or in the logs | with the stub provider as the endpoint, capture the outbound request: require no profile block when the request carries no profile, and no access token, profile id or admin token anywhere in the captured payloads or the API container logs | P0 |
| AC-12 | Operator endpoints are authenticated | `curl -s -o /dev/null -w '%{http_code}' $API/ops/audit` must return 401, and the same with a wrong token must return 401; with a blank `ADMIN_TOKEN` the control endpoints must return 503 | P0 |
| AC-13 | Answers are usable as written, and never decide eligibility | SME scores 200 sampled answers (first 200 citizen-facing and shadow answers after week 2 start, stratified English/Hindi): at least 70 percent usable without correction; any answer that states an eligibility determination fails the pilot overall | P0 |
| AC-14 | Handling time actually falls | from ticket timestamps plus the daily containment flag: containment >= 0.20 and median handling time saved >= 3 minutes per query | P1 |

Stop conditions, effective immediately, no vote required: an answer that reached a citizen stating an
eligibility determination; a fabricated quote presented as verified; citizen identifiers found in an
outbound payload or log. On any of these, engage the kill switch, preserve the evidence, and issue a
written incident note within two working days.

## 5. Prerequisites we require from the customer

| # | Prerequisite | Why | Owner | Due |
| --- | --- | --- | --- | --- |
| P1 | Host VM: 8 vCPU, 16 GB RAM, 250 GB free disk, Docker Engine + Compose plugin | preflight blockers `PF-010` to `PF-022` fail otherwise | IT | before week 1 |
| P2 | Egress decision: either an allowlist for the model provider and the container registry through the proxy, or the air-gap bundle path with a defined transfer process and a signature verification step | `PF-040` to `PF-045`; a TLS-inspecting proxy needs their root CA installed, never a disabled check | IT | before week 1 |
| P3 | `.env` filled by their staff: `DATABASE_URL`, `GROQ_API_KEY`, `ADMIN_TOKEN`. The admin token is generated and held by them; we never hold it | operator controls are disabled when `ADMIN_TOKEN` is blank (503), by design | IT | week 1 |
| P4 | Persistent path mounted for `var/` | the kill switch state lives there and must survive container replacement | IT | week 1 |
| P5 | 200 real queries exported and redacted (question, language, channel) in an agreed file format | the retrieval gate and the pilot tests run on their queries, not ours | Programme | end of week 1 |
| P6 | Named people: 1 programme owner (decision maker), 2 IT operators for the on-call rota, 2 subject-matter reviewers (about 40 hours each over 4 weeks), 6 to 10 agents, 1 data-protection contact | without reviewers there is no AC-13, without operators there is no handover | Programme | week 1 |
| P7 | Written corpus scope: the named schemes to be hand-verified, and the officer who signs each record | stops the corpus becoming an open-ended commitment | Programme | week 1 |
| P8 | Written rule on citizen disclosure ("decision support, verify at the official source") and what agents may say | AC-13 and the escalation path depend on it | Programme | week 2 |
| P9 | Written definition of containment, agreed before measurement starts | otherwise AC-14 is arguable after the fact | Programme + Helpdesk | week 2 |
| P10 | Change window for the upgrade rehearsal, or a signed waiver | AC-10 | IT | week 3 |

## 6. Go/no-go rule

Evaluated at the end of week 4, on the evidence in the pilot log, by the programme owner, and
recorded in the final report. The rule is written to be applied mechanically.

```
IF every P0 criterion passes
   AND AC-05 passes (Hit@4 >= 0.80 on the customer query set)
   AND AC-13 passes (>= 70 percent usable, zero eligibility determinations)
   AND AC-14 passes (containment >= 0.20, median saving >= 3 minutes)
THEN GO
   -> production rollout of the same single-tenant topology on the customer host,
      with the corpus verification plan and its named sign-off attached.

ELSE IF every P0 criterion passes
   AND AC-13 is between 60 and 70 percent
   AND AC-14 containment is >= 0.10
THEN CONDITIONAL
   -> extend by two weeks with no new scope; re-measure AC-13 and AC-14 once on
      the same instrument; apply this rule again to the new measurements.
      One extension only.

ELSE NO-GO
   -> the pilot ends at the end of week 4. The install is removed or left in
      retrieval-only mode, at the customer's choice. The written reason (the
      criterion that failed and its measured value) is handed over with the logs.
```

Hard rules that override the branch above: any single failed P0 criterion is a NO-GO unless the
failure is a documented prerequisite the customer did not deliver, in which case the decision is
CONDITIONAL with the undelivered prerequisite named as the single action. Any stop condition in
section 4 is a NO-GO for the citizen-facing channel, and a re-entry requires a written corrective
plan accepted by the data-protection contact. No automatic renewal and no automatic extension.

## 7. Risks to the four weeks

| Risk | Signal | Response |
| --- | --- | --- |
| Egress from the API VLAN is refused | `PF-042` / `PF-044` blockers on day 1 | switch to the air-gap bundle path in week 1; that is a planned path, not a failure |
| Free-tier token ceiling throttles peak volume | rising degraded answers during peak hours on `/ops/status` | raise `RATE_LIMIT_RPM` deliberately, add a second endpoint via `/ops/provider`, or accept retrieval-only answers during peaks and say so |
| Reviewer time is not released | AC-13 sample below 200 by end of week 3 | escalate to the programme owner in the weekly note; the criterion cannot be scored without it |
| Corpus verification slips | fewer than the named schemes signed by end of week 2 | reduce the named list in writing rather than pretending coverage |
| Proxy TLS inspection breaks the provider call | `PF-045` warning, provider failures in `/ops/status` | install their root CA on the host; never disable verification |
