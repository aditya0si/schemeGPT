# 06 Ops one-pager

For the on-call operator. Print it. The API binds to `127.0.0.1:8000` on the host, so run these from
the host or over an SSH tunnel, not from a laptop. Endpoint behaviour on this page is
measured (from this repository); the escalation rungs are a proposal (assumption (yours to change))
for the customer to amend.

```bash
export API=http://127.0.0.1:8000
export ADMIN_TOKEN='<the customer-held operator token>'   # never paste this into a ticket
```

## 1. Triage in 60 seconds

```bash
curl -s $API/health                     # status ok, plus ai state and breaker state
curl -s $API/ops/status | python3 -m json.tool
docker compose ps                       # both containers up, api healthy
```

Read `/ops/status` like this:

| Field | What it tells you | Action |
| --- | --- | --- |
| `ai.state` | `enabled` or `disabled` (a human decision, not an outage) | if `disabled`, find out who and why before changing it |
| `breaker.state` | `closed` normal, `open` provider failing, `half_open` one probe in flight | see section 4 |
| `degraded_answers.*` | totals: degraded answers served, breaker rejections, provider failures versus successes | rising `breaker_rejections` means requests were not wasted on a failing provider |
| `provider.endpoint` | where generation is currently going, credentials and query strings masked | compare against the agreed gateway URL |
| `version` | build identity of the running code | confirm before and after an upgrade |

## 2. Operator endpoints and exact commands

| Endpoint | What it does | Command |
| --- | --- | --- |
| `GET /health` | liveness plus `ai` and `provider_circuit`. Stays 200 while generation is off, on purpose: a human pressed a switch, nothing is down, do not restart the container for it | `curl -s $API/health` |
| `GET /ops/status` | public, safe snapshot: switches, breaker, counters, masked endpoint. No reasons, no error text | `curl -s $API/ops/status \| python3 -m json.tool` |
| `GET /metrics` | aggregate counters and latency percentiles. No per-request data | `curl -s $API/metrics \| python3 -m json.tool` |
| `GET /coverage` | corpus transparency: totals by provenance, per-jurisdiction counts | `curl -s $API/coverage \| python3 -m json.tool` |
| `GET /ops/audit` | last 50 operator actions: time, action, actor, reason (admin only) | `curl -s $API/ops/audit -H "X-Admin-Token: $ADMIN_TOKEN" \| python3 -m json.tool` |
| `POST /ops/ai` | turn generation off. Answers become retrieval-only, assembled from verbatim source excerpts, still cited. Persists across restart (admin only) | `curl -s -X POST $API/ops/ai -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"enabled": false, "reason": "provider incident", "actor": "oncall-<name>"}'` |
| `POST /ops/ai` | turn generation back on | `curl -s -X POST $API/ops/ai -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"enabled": true, "reason": "provider recovered", "actor": "oncall-<name>"}'` |
| `POST /ops/provider` | route generation through a gateway, egress proxy or secondary provider, at runtime, in memory only | `curl -s -X POST $API/ops/provider -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"base_url": "https://llm-gw.customer.internal/groq/v1", "reason": "provider incident", "actor": "oncall-<name>"}'` |
| `POST /ops/provider` | clear the override and return to the configured endpoint | `curl -s -X POST $API/ops/provider -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"base_url": "", "actor": "oncall-<name>"}'` |
| `POST /query` | smoke test a real question, in either language | `curl -s -X POST $API/query -H 'Content-Type: application/json' -d '{"question": "PM-KISAN ke liye kaun eligible hai?", "language": "hi"}'` |
| `POST /query/stream` | streamed form: `sources` then `token` events then `done` | `curl -sN -X POST $API/query/stream -H 'Content-Type: application/json' -d '{"question": "What documents do I need for PM-JAY?"}'` |
| `POST /ingest` | re-ingest the Markdown corpus (admin only). Idempotent: unchanged chunks are skipped, vectors are never deleted | `curl -s -X POST $API/ingest -H "X-Admin-Token: $ADMIN_TOKEN"` |

`mode` in a `/query` response: `live` is a generated answer; `degraded` means generation is off and
the answer is assembled from source excerpts; `demo` means no live provider is configured. A
`degraded` or `demo` answer is still cited and still useful. Tell the desk which one they are
getting rather than letting them assume.

## 3. Deploy-side commands

```bash
docker compose ps
docker compose logs --tail=200 api
python3 deploy/field/preflight.py --label <site> --json deploy/field/reports/preflight-<site>.json
bash deploy/field/upgrade.sh --to-version <version>     # snapshots db and env, gates on health, auto-rolls back
bash deploy/field/rollback.sh                            # back to the recorded previous version
python3 deploy/field/drill.py --phases A,B,C,D,E,F,G     # rehearse; writes docs/evidence/FIELD-DRILL.md
```

Runbook with full detail: `docs/FIELD-DEPLOY.md` (preflight, bundle, install, upgrade and rollback,
operate, rehearse, limits). Measured evidence of past runs is in `docs/evidence/FIELD-DRILL.md`; that
recorded run completed phase A and exited 127 on phase B, so the drill is a rehearsal to complete, not
a certificate to cite.

## 4. Escalation ladder

| Rung | Signal | Do this |
| --- | --- | --- |
| 1 | `provider_failures` rising, breaker `closed` | provider is degraded but serving. Note it, keep watching, check the provider status page |
| 2 | breaker `open` | degraded answers are live now. If the desk cannot accept degraded answers for the task at hand, engage the kill switch and tell them plainly what they are getting |
| 3 | breaker `half_open` repeatedly, or `open` for more than one cooldown cycle | route with `POST /ops/provider` to the secondary or the customer gateway; if that fails, disable generation; escalate with `last_error_type` and the timestamps from `/ops/status` |
| 4 | suspected wrong or stale source content | kill switch first, discussion second. That ordering is the whole point of the control |
| 5 | an answer that reached a citizen stated an eligibility determination, or a fabricated quote was shown as verified | kill switch, preserve the evidence (question, answer, cited source, timestamp), notify the programme owner and the data-protection contact, written incident note within 2 working days |

## 5. Never

- Never restart the containers to "fix" degraded answers. Degraded means a human switched generation
  off or the breaker is protecting the provider. Restarting hides the signal and does not change it.
- Never disable TLS verification for the provider or the proxy. A certificate problem is fixed by
  installing the customer's root CA on the host.
- Never leave generation disabled without a reason string: the audit trail is the only record of why.
- Never edit `.env` on the live host without a change window; the durable provider endpoint lives
  there, and an upgrade gate will roll back a bad setting and confuse the picture.
- Never delete `deploy/field/logs/` or the preflight JSON records. They are the deployment history.
- Never paste `$ADMIN_TOKEN` into a ticket, a chat message or a log.
