# Field deployment runbook

This is the runbook for putting SchemeGPT on a machine you do not control, and
for keeping it correct once it is there. It covers five things, in the order you
will need them: check the host, build a deliverable, install, change a version,
and operate. Everything here is executable from the repository or from a
delivery bundle; nothing requires a paid account.

Measured results of a full rehearsal (install → upgrade → broken release →
kill switch → provider outage → no egress) are in
[`evidence/FIELD-DRILL.md`](evidence/FIELD-DRILL.md), produced by
`deploy/field/drill.py`.

```
deploy/field/
  preflight.py       host doctor: PF-0xx findings, air-gap mode, JSON record
  bundle.sh          build the delivery bundle (images + checksums + signature)
  verify.sh          verify a bundle before loading anything
  install.sh         load, preflight, start, health-gate, smoke, record
  upgrade.sh         snapshot, gate, smoke, row-count check, auto-rollback
  rollback.sh        image rollback (+ optional env/database restore)
  stub_provider.py   an OpenAI-compatible provider that can be made to fail
  drill.py           rehearses all of the above against a real deployment
  lib.sh             shared helpers (health gate, deploy records, snapshots)
  reports/           preflight + drill JSON records (tracked)
  logs/              one JSON per deploy action (ignored; copy the ones you keep)
  state/deployed.json  what version is running and what it replaced
```

## 0. What "deployed" has to mean

Three things, because a customer will ask for all three:

1. **It runs where they need it.** Their VPC, their on-prem host, their network
   policy, their proxy.
2. **It can be changed without a drama.** A new version plus a working rollback,
   rehearsed rather than hoped for.
3. **It can be switched off.** An operator control that stops model generation
   while leaving the service up, honest, and useful.

## 1. Preflight the host (before you promise anything)

```bash
python3 deploy/field/preflight.py --label "state-gov-prod-01" \
    --json deploy/field/reports/preflight-state-gov-prod-01.json
```

Exit codes: `0` go, `1` blockers, `2` go with warnings. Read the blockers before
touching the install — they are the failure modes that cost you a day:

| Code | Check | Why it matters |
| --- | --- | --- |
| `PF-011` | Docker daemon reachable | installed-but-not-running is the most common first failure |
| `PF-020` | free disk | 12 GB minimum: images, Postgres growth, model cache |
| `PF-021` | memory | the API holds a 470 MB embedding model; 3.5 GB is the floor |
| `PF-030..032` | ports 8000/8501/3000 | a bound port makes the install fail in front of the customer |
| `PF-040/041` | DNS for registry and provider | in an air-gap install use `--airgap` and this becomes informational |
| `PF-042/044` | TCP 443 egress | the egress policy is the usual reason a pilot dies on day one |
| `PF-045` | TLS trust chain | corporate TLS inspection needs their root CA installed, never `--insecure` |
| `PF-046` | clock skew | measured against the provider's `Date` header; skew breaks TLS and JWT |
| `PF-050..052` | `.env` keys present | presence only; values are never printed |
| `PF-053` | operator state path | the kill switch persists here; mount it on a volume |
| `PF-060` | images loaded | in air-gap mode, images arrive from the bundle |

Run it again after install and attach the JSON to the engagement record: it
documents the host's state on the day you stood it up.

## 2. Build a deliverable (connected side)

```bash
bash deploy/field/bundle.sh --version v2.0.0 --sign
```

Produces `deploy/field/bundles/schemegpt-bundle-v2.0.0/` and a tarball beside
it. The bundle contains the API, database and (optionally) web images as
tarballs, a `MANIFEST.json` naming each image by immutable ID and digest, a
`SHA256SUMS` file, and the install scripts.

`--sign` adds a detached RSA-3072/SHA-256 signature over `SHA256SUMS` plus the
public key, with `SIGNING.md` stating exactly what that does and does not prove.
Read that file before you let anyone describe it as a chain of trust: the key is
generated for the build and destroyed, so it proves *integrity*, not identity.
A real engagement holds the key (or uses `cosign` with an OIDC identity) and the
customer pins the public key out of band.

Scripts are LF-pinned (`.gitattributes`) and re-stripped when bundled: a CRLF
shebang on a Linux host fails with `bad interpreter: ...^M`.

## 3. Install (customer side of the air gap)

```bash
tar xzf schemegpt-bundle-v2.0.0.tar.gz && cd schemegpt-bundle-v2.0.0
./verify.sh --signature          # checksums + signature, before loading anything
./install.sh --airgap            # load, preflight, start, health-gate, smoke
```

`install.sh` refuses to start without a `.env`: it copies `.env.example` and
stops so a human supplies `DATABASE_URL`, `GROQ_API_KEY` and `ADMIN_TOKEN`.
Secrets are never generated silently — a deployment that invents its own admin
token is a deployment nobody can audit.

The health gate is `/health` **and** `/ops/status`, and it accepts `/ops/status`
returning 404 so this kit can upgrade *from* an older build that predates the
operator control plane. `/health` returning `ok` while AI is disabled is
deliberate: a human pressed a switch, nothing is down, and the container must
not be restarted for it.

After it comes up:

```bash
curl -s http://127.0.0.1:8000/ops/status | python3 -m json.tool
```

## 4. Change a version (and be able to undo it)

```bash
bash deploy/field/upgrade.sh --to-version v2.0.1
```

In order:

1. **Snapshot the database** (`pg_dump` into `deploy/field/backups/`, refused if
   the dump looks empty) and **snapshot the environment file** — a release is
   code *and* configuration, and a bad setting is a more common cause of a failed
   release than bad code.
2. Pin the new image and recreate the API container.
3. **Gate on health**, then on a real product call (`POST /query`), not on "the
   container started".
4. **Compare vector-store row count before and after.** A migration that drops
   rows is a data incident and no health check will see it.
5. On any failure: **roll back automatically** — previous image, previous
   environment — and write both records.

```bash
bash deploy/field/rollback.sh                                   # to the recorded previous version
bash deploy/field/rollback.sh --to-version v2.0.0 --restore-db deploy/field/backups/<file>.sql
```

The image swap is always safe. `--restore-db` is destructive and deliberately
explicit: a schema migration is not undone by running the old image. Roll the
code back first, confirm health, then decide about the data.

Every action writes `deploy/field/logs/<timestamp>-<action>.json` and updates
`deploy/field/state/deployed.json`. Keep those: they are the engagement's
deployment history.

## 5. Operate

### Stop generation without stopping the service

```bash
curl -s -X POST http://127.0.0.1:8000/ops/ai \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"enabled": false, "reason": "stale corpus pending re-verification", "actor": "oncall-aditya"}'
```

What the customer sees while it is off: the same endpoint, HTTP 200, `mode:
"degraded"`, and an answer assembled from verbatim source excerpts with the
citation lines verified mechanically — no generated prose, no pretending. The
decision is persisted to `OPS_STATE_FILE` and survives a restart or a redeploy;
re-enable with `{"enabled": true}`. Reasons are stored in the audit trail
(`GET /ops/audit`, admin only) and never exposed on the public status endpoint.

### Understand why answers are degraded

```bash
curl -s http://127.0.0.1:8000/ops/status | python3 -m json.tool
```

`ai.state`, `breaker.state` (`closed` / `open` / `half_open`), `trips`,
`last_error_type`, and the degraded/refusal counters. Provider error *text* is
never included; exception types are.

### Route generation through the customer's gateway

```bash
curl -s -X POST http://127.0.0.1:8000/ops/provider \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"base_url": "https://llm-gw.customer.internal/groq/v1", "actor": "field-eng"}'
```

Runtime and in-memory by design: the durable form is `GROQ_API_BASE` in the
environment, so nobody with API access alone can permanently repoint a
deployment's traffic. Clearing it (`{"base_url": ""}`) restores the configured
endpoint. Setting it invalidates the cached chain so the change takes effect
immediately rather than at the next restart.

### When the provider is failing

The circuit breaker opens after `BREAKER_FAILURE_THRESHOLD` consecutive
failures (default 3) and stops calling a provider that is already failing for
`BREAKER_RESET_TIMEOUT_S` (default 30s), then sends exactly one probe. During
that window every answer is retrieval-only. Watch `provider_failures` versus
`breaker_rejections`: the second number is requests the deployment *did not*
waste on an unhealthy provider.

Escalation ladder:

1. `provider_failures` rising, breaker `closed` → provider is degraded but
   serving; check status page, keep monitoring.
2. Breaker `open` → degraded answers are live. If the customer cannot accept
   degraded answers for the task at hand, engage the kill switch and tell them
   plainly what they are getting.
3. Breaker `half_open` repeatedly, or `open` for more than one cooldown cycle →
   route to a secondary endpoint (`/ops/provider`) or disable generation and
   escalate to the provider with the `last_error_type` and the timestamps from
   `/ops/status`.
4. Data suspicion (wrong or stale source content) → kill switch first, discuss
   second. That ordering is the whole point of the control.

## 6. Rehearse before you need it

```bash
python3 deploy/field/drill.py --phases A,B,C,D,E,F,G
```

Runs a real deployment through: installing the previous release, upgrading,
shipping a deliberately broken release (which must fail the gate and roll back
by itself), engaging the kill switch and restarting the container to prove the
switch survives, a sustained provider outage against a local stub
(`stub_provider.py`), a no-egress window, and an air-gap preflight. It writes
`docs/evidence/FIELD-DRILL.md` and a JSON record.

Nothing in the drill calls a real model provider — the stub is pointed at
through `/ops/provider` — so it is deterministic, free, and safe to run on a
customer's staging host.

## 7. Limits and honest caveats

- The default provider is Groq's free tier: **8k tokens/minute**, which bounds
  throughput per instance. A pilot sized above that needs a paid tier or a
  second endpoint via `/ops/provider`.
- Answers are grounded **only** in the ingested corpus. If a scheme is not in
  the corpus the system says so; it does not guess, and it is not a legal or
  eligibility authority.
- A large share of the corpus is `directory_seed` (national portal discovery
  entries), not hand-verified records. Anything customer-facing must state the
  split; `GET /coverage` reports it.
- Single-host Compose with two containers is not high availability. An upgrade
  has a short downtime window (the API container is recreated). If the customer
  needs zero-downtime, that is a different deployment topology, and the health
  gate and rollback logic here are the parts you keep.
- The kill switch and the breaker are per-instance controls, not fleet controls.
