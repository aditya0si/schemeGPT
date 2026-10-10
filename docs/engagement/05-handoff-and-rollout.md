# 05 Handoff and rollout

The engagement is finished when the customer's own staff can install, operate, break and recover the
system without us in the room. This document is the plan for getting there: enablement, what changes
for people, who escalates to whom, and the assets that change hands. Durations, cadences, competence
evidence and the 30/60/90 windows below are proposals: assumption (yours to change). Product
behaviour referenced here is measured (from this repository).

## 1. Ownership after handover

| Role | Owns | Named by |
| --- | --- | --- |
| Programme owner | the go/no-go decision, the corpus scope, the disclosure rule | customer |
| IT operator (2 people, on call) | host, install, upgrades, rollback, preflight records, backups | customer |
| On-call operator | first response: kill switch, breaker state, degraded answers | customer |
| Subject-matter reviewer (2 people) | verified records, answer disputes, the usability sample | customer |
| Helpdesk supervisor | agent behaviour, the weekly numbers, the escalation ladder | customer |
| Data-protection contact | the security packet acceptance note, retention decisions | customer |
| Vendor | pilot delivery, then on-call escalation until the exit criteria are met | vendor |

Two access facts to state plainly at handover: the `ADMIN_TOKEN` is generated and held by the
customer, and the model provider key is theirs, so both regressions (the vendor can no longer operate
the instance, and the vendor can no longer spend their provider quota) happen by key rotation, not by
promise. Rotate both on the day the vendor's on-call window closes.

## 2. Enablement plan

| Audience | Content | Duration | Competence evidence (proposal) |
| --- | --- | --- | --- |
| IT operators (2) | install path, `deploy/field/preflight.py` codes and severities, bundle verification, `upgrade.sh` and `rollback.sh`, the health gate, where deploy records and snapshots are written | 3 hours, hands-on | runs an upgrade and a rollback unaided on staging, reads a preflight JSON aloud and names each blocker and its fix |
| On-call operators (4 to 6) | `06-ops-one-pager.md` end to end: kill switch, circuit breaker states, degraded versus demo answers, what `/health` does and does not say | 90 minutes | performs the kill-switch drill unaided, explains why `/health` stays 200 while generation is off |
| Helpdesk agents (6 to 10, then the wider desk) | what the system is and is not, how to read the citation block, what `directory_seed` means, the `verified` and `unverified` quote flag, the disclosure script, how to file feedback with `POST /feedback` | 2 hours plus a supervised first shift | answers 10 scripted queries and correctly flags a deliberately weak answer, including one where the corpus has no record |
| Subject-matter reviewers (2) | the record template (`docs/scheme-record-template.md`), the corpus rules (`docs/data-operations.md`), `scripts/validate_data.py`, the usability rubric behind AC-13 | 3 hours | signs one new verified record that passes the validator, and scores a calibration set of 10 answers within one point of the vendor's score |
| Supervisors and managers (2) | reading `GET /metrics` and `GET /ops/status`, the weekly numbers, the escalation ladder, what a repeated bad answer triggers | 1 hour | produces the weekly note once from real data |
| Data-protection contact | `03-security-packet.md`, especially sections 3, 9 and 12 | 1 hour | returns the acceptance note or the amendment list in writing |

Materials the customer keeps: this pack, the deployment runbook `docs/FIELD-DEPLOY.md`, the data
runbook `docs/data-operations.md`, the AI stack reference `docs/AI-ENGINEERING.md`, the printed
on-call page, and the preflight and drill JSON records as the deployment history.

## 3. What changes for people (change management)

| Change | Who feels it | How it is handled |
| --- | --- | --- |
| Agents stop reading PDFs first and read a cited answer instead | front-line agents | 2-hour training, then a supervised first shift; the citation block is the new habit, and it is what makes the answer defensible |
| Answers now carry a verified or unverified quote flag | agents and supervisors | plain rule: an answer with an unverified quote, or no matching record, goes to a human before it goes to a citizen |
| The system never decides eligibility | agents and citizens | written disclosure rule (a pilot prerequisite); the agent script says the system explains published criteria and points to the official source |
| Directory-seed records appear in results and must not be read as eligibility | agents and reviewers | short training item plus the provenance field shown on every source |
| A new escalation path exists | agents, supervisors, IT | printed ladder (section 4) at every desk; rehearsed in week 3 |
| Supervisors get a new weekly number | supervisors | one page per week: answered count, degraded count, unverified-quote count, escalation count, top unanswered questions |
| IT inherits a new service | IT operators | two named operators trained, on-call rota live from week 3, runbook walked through hands-on |
| Corpus updates become a recurring duty | SMEs | monthly corpus refresh, quarterly re-verification of the named schemes, signed records |

Answer disputes: an agent flags a bad answer through a single agreed channel; the SME reviews it
within 2 working days; if the corpus is wrong, the record is corrected and re-ingested, and the case
is added to the regression set (the repository already has the path: `POST /feedback` records it and
`scripts/feedback_to_eval.py` turns curated cases into eval questions). Thumbs-up cases grow the
suite; thumbs-down cases become the dispute queue. No silent fixes.

Release and change cadence (proposal): software upgrades only inside the customer's change window,
always via `upgrade.sh` with the automatic rollback armed, never by hand on the live host; corpus
refreshes monthly; a change freeze for the two weeks before each peak window, with the current bundle
version pinned and recorded in `deploy/field/state/deployed.json`.

## 4. Escalation path

| Level | Trigger | Who acts | First action | Evidence to capture |
| --- | --- | --- | --- | --- |
| L1 | an answer looks wrong, or a citizen disputes it | helpdesk agent | flag it, do not improvise an eligibility answer | the question, the answer, the cited source |
| L2 | degraded answers rising, or the same wrong answer twice | helpdesk supervisor, then on-call operator | check `GET /ops/status`; if the corpus is in doubt, engage the kill switch first and discuss second | `/ops/status` snapshot, timestamp, `/metrics` counters |
| L3 | provider failures, breaker open across a cooldown cycle, throughput throttling | IT operator on call | route to the secondary or gateway endpoint with `POST /ops/provider`, or leave generation off and tell users what they are getting | `last_error_type`, timestamps, gateway logs |
| L4 | breaker open more than one cooldown, or the fix needs code or corpus changes | vendor on-call (during the pilot window) | reproduce on staging, then ship through the normal upgrade path | deploy records in `deploy/field/logs/` |
| L5 | any stop condition in `02-pilot-scope.md` section 4 has occurred | programme owner plus data-protection contact | generation stays off until a written corrective plan is accepted; incident note within 2 working days | kill-switch audit entries, the offending answer, the source record |

The ordering rule that matters: suspected bad data means kill switch first, discussion second. The
switch is persisted (`var/ops_state.json`) and survives a restart, so nobody has to hold the line
while a deploy happens.

## 5. Handover sequence and exit criteria

Staged, in this order, with a named owner for each stage:

1. Shadow (week 2): vendor operates, customer watches.
2. Joint operation (week 3): customer operators run the drills, vendor is on the call but not at the
   keyboard.
3. Reverse shadow (week 4): customer operates, vendor observes and does not touch the keyboard.
4. Independent (end of week 4): customer operates alone; vendor on call for a fixed window agreed in
   writing.

Exit criteria, all required:

| # | Exit criterion | Evidence |
| --- | --- | --- |
| E1 | both IT operators have run an upgrade and a rollback unaided | deploy records with a customer actor in the notes |
| E2 | the on-call rota has performed the kill-switch drill and the outage drill on a business day | drill sheet with timestamps and observed `breaker.state` transitions |
| E3 | `deploy/field/drill.py` has been run end to end to a clean pass on staging, with the JSON report kept | drill report; note that the currently recorded run completed phase A and exited 127 on phase B, so this must be re-run, not cited |
| E4 | the SME sample behind AC-13 is complete and the answer-dispute path has been exercised at least twice with corrections signed | review log with two closed disputes |
| E5 | the customer holds `ADMIN_TOKEN` and the provider key; vendor credentials rotated out | written key-handover note |
| E6 | the security packet acceptance note (or the amendment list) is signed | signed page |
| E7 | the deployment history and the pilot log are archived under the customer's records policy | archive path recorded |

## 6. Assets handed over

| Asset | Where it lives | Note |
| --- | --- | --- |
| Install on the customer host | one VM, Docker Compose | API bound to localhost, web behind their reverse proxy |
| Operator state | `var/` on a mounted volume | holds the kill switch; must survive container replacement |
| Deploy history | `deploy/field/logs/`, `deploy/field/state/deployed.json` | one JSON per action; this is the audit trail for changes |
| Preflight and drill records | `deploy/field/reports/` | attach to the engagement record |
| Corpus and the verification rules | `data/`, `docs/data-operations.md`, `docs/scheme-record-template.md` | the monthly and quarterly duties follow from these |
| Eval set and results | `eval/` | the regression gate that protects quality after we leave |
| Runbook | `docs/FIELD-DEPLOY.md` | sections: preflight (1), bundle (2), install (3), upgrade and rollback (4), operate (5), rehearse (6), limits (7) |
| On-call page | `06-ops-one-pager.md` | print it; it is designed to be followed under pressure |
| Public key for bundle verification | held by the customer, pinned out of band | the build key is generated for the build and destroyed, so it proves integrity, not identity |
| Pilot log and measurement analysis | agreed file format | the raw logs go to the customer, not just the summary |

## 7. After the pilot: 30, 60, 90 (proposal)

| Window | Customer action | Vendor role |
| --- | --- | --- |
| 0 to 30 days | run the corpus refresh cycle once, complete the first quarterly verification sweep, produce the weekly note four times | on call for L4, no standing access |
| 30 to 60 days | decide the staffing consequence named in `04-roi-model.md` section 7 (redeployment or hiring decision), extend the answer-dispute path to all districts | review the first monthly numbers, report on whatever the numbers actually say |
| 60 to 90 days | review the security packet gaps that section 9 of `03-security-packet.md` lists, decide which to fund (secret management, retention jobs, per-user operator identity, SIEM feed) | scoped separately, and only against a written list |

## 8. Limits of this handover

- There is no product-level incident process, no support contract and no SLA in this pack. Post-pilot
  support terms are a separate document; say that out loud rather than implying otherwise.
- The operator audit trail holds at most 50 entries in memory and is lost on restart; the durable
  record of change is the deploy logs, which are files on the host.
- No per-user operator identity exists: the admin token is shared, and the audit `actor` field is
  typed by hand. Until that changes, treat operator access as a small trusted group and rotate the
  token when the group changes.
- The failure drill has not yet produced a clean end-to-end pass in a recorded run, so E3 is a real
  task in week 4, not a formality.
