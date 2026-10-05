# Interview defence pack — SchemeGPT

You will be asked about this project by people who have read the README and by
people who have not. This document is the second group's worst case: every
number, every decision, and the alternatives that were rejected, with the
command that reproduces each claim.

Written to be read the night before an interview, not skimmed.

---

## 1. The sixty-second version

SchemeGPT answers questions about Indian government welfare schemes in English,
Hindi and Hinglish, with citations that are *checked* rather than trusted. The
differentiator is not the RAG pipeline; it is what happens around it:

- **Answers are grounded and provable.** Every quoted line is verified by exact
  normalized-substring matching against the retrieved source document. A model
  cannot invent a clause, an amount or an eligibility rule and have it survive.
- **The system can be turned down honestly.** An operator kill switch stops
  generation and the service keeps answering from retrieved source text, in
  labelled degraded mode, with the same citation guarantees.
- **It can be deployed where the customer actually is.** Air-gap install bundle
  with checksums and a signature, a host preflight doctor that looks for the
  things that kill pilots (TLS interception, clock skew, egress policy), and an
  upgrade that snapshots both the database and the configuration and rolls back
  by itself when a release fails its gate.

If you remember one sentence: *it is a RAG system built the way you build
something a government department will have to run without you.*

---

## 2. Architecture you must be able to draw on a whiteboard

```
                     ┌──────────────────────────────────────────┐
  citizen ──────────▶│ Next.js 15 web  (server-side proxy)      │
  (EN / HI / mixed)  │ Streamlit demo (secondary client)        │
                     └───────────────┬──────────────────────────┘
                                     │  POST /query · /query/stream (SSE)
                     ┌───────────────▼──────────────────────────┐
                     │ FastAPI                                  │
                     │  1 semantic cache lookup (pgvector)      │
                     │  2 operator gate  ◀── kill switch        │
                     │                     ◀── circuit breaker  │
                     │  3 hybrid retrieval → RRF fusion         │
                     │  4 generation (Groq)  ─────┐             │
                     │  5 quote verification      │             │
                     └───────────────┬────────────┴─────────────┘
                                     │
        ┌────────────────────────────┼─────────────────────────────┐
        │                            │                             │
┌───────▼────────┐        ┌──────────▼─────────┐        ┌──────────▼─────────┐
│ PostgreSQL 16  │        │ Groq (gpt-oss-120b │        │ Operator layer     │
│ + pgvector     │        │ + 20b for routing) │        │ /ops/status        │
│ + tsvector     │        │ gateway-overridable│        │ /ops/ai            │
│ 2,105 records  │        └────────────────────┘        │ /ops/provider      │
└────────────────┘                                      │ /ops/audit         │
                                                        └────────────────────┘
```

Flow in words, because the drawing is not the answer:

1. **Cache**: a semantically equal question with the same profile hash is served
   from the stored live answer (cosine ≥ 0.95, same language + profile).
2. **Operator gate**: the kill switch and the circuit breaker are consulted
   *before* any provider call. Either can short-circuit the request into the
   retrieval-only path.
3. **Retrieval**: three channels — dense pgvector (`multilingual-e5-small`,
   384-d), PostgreSQL `tsvector` full-text, and a lexical scheme-name channel
   that anchors acronyms like `pm-sym` — fused with Reciprocal Rank Fusion, then
   the top-4 source-diverse documents.
4. **Generation**: a per-language stuff-documents chain at temperature 0, with a
   bounded `max_tokens`, called through a client whose base URL can be repointed
   at a customer gateway at runtime.
5. **Verification**: the answer's `> quote [source, data_status]` lines are
   parsed and each is checked against the retrieved content by normalized
   substring match, with a tight similarity fallback.

The three modes an answer can come back in — `live`, `degraded`, `demo` — and
what each one honestly claims, is the single most important thing to be able to
explain. `demo` means "no key configured, this is a canned example"; `degraded`
means "generation is off or the provider is failing, these lines are verbatim
excerpts from retrieved documents"; `live` means "a model wrote this and the
quotes in it were verified".

---

## 3. Numbers, and where each one actually came from

| Claim | Value | Where it comes from | Reproduce |
| --- | --- | --- | --- |
| Corpus size | 2,105 markdown records (6 verified central, 36 state/UT seeds, 2,063 portal imports) | `data/` tree; each record carries `data_status` | `ls data/schemes/*.md data/states/*.md data/myscheme/*.md \| wc -l` |
| Vector store | reported live by the deployment | PostgreSQL `langchain_pg_embedding` | `docker compose exec -T db psql -U scheme -d schemegpt -tAc "select count(*) from langchain_pg_embedding"` |
| Retrieval quality | Hit@4 = 0.875, MRR@4 = 0.796875 over 16 EN/HI/Hinglish/profile cases (lexical tie-breaking was plan-dependent; now deterministic, and a trust-aware logical-document dedup prefers the hand-verified copy over the auto-imported duplicate) | Required CI eval gate on the full corpus; floors Hit@4 ≥ 0.85, MRR@4 ≥ 0.60 | `python -m eval.retrieval_gate` |
| Test suite | 125 pytest tests locally, no DB, no network, no LLM | `tests/` | `python -m pytest -q` |
| CI | 4 jobs: data validation, unit tests, field kit, web build (+ weekly eval gate) | `.github/workflows/ci.yml`, `eval.yml` | `gh run list --limit 5` |
| Provider ceiling | 8k tokens/minute on the free tier — a real throughput bound per instance | provider plan, stated in `docs/FIELD-DEPLOY.md` | `GET /metrics` token counters under load |

**Say the caveat with the number.** "Hit@4 0.875 on 16 curated cases across
three languages" is a claim about those cases, not about the corpus. The earlier
0.875 was plan-dependent — the lexical channel broke ties on unspecified
Postgres row order — so it was corrected to the reproducible 0.8125 rather than
kept. That reproducible figure exposed a real retrieval defect: the same scheme
was indexed twice and source-level diversity let the auto-imported copy displace
the hand-verified one. Capping one chunk per logical document and preferring the
higher-trust copy is a correctness fix, not a tuned knob, and it brings the gate
back over its 0.85 floor with no case regressing. The deterministic CI gate is
what stops it drifting.

### Measured on a real deployment, not estimated

From `deploy/field/drill.py` against a Docker Compose stack — a release that
predates the operator control plane being upgraded, broken and rolled back, then
put under provider failure and total loss of egress. Raw JSON in
`deploy/field/reports/`, summary in `docs/evidence/FIELD-DRILL.md`.

| What | Measured | What it buys you in the room |
| --- | --- | --- |
| Install the previous release | healthy in **6.06s** | the baseline is a genuinely older build: `/ops/status` → 404 |
| Upgrade to this release | exit 0 in **65.36s** | snapshot → pin → recreate → gate → smoke → recorded |
| Broken release | exit 1 after **196.32s**, auto-rolled back, API answering `live` | the gate protects the deployment, and the rollback restores image *and* configuration |
| Kill switch → degraded answers | **0.16s** per answer, 4 sources, citations verified **3/3** | the service stays useful and honest with generation off |
| Kill switch survives a restart | still `disabled`, answers still `degraded`, healthy in **5.07s** | a switch that a redeploy silently undoes is not a switch |
| Circuit breaker opens | **2.32s** into sustained 429s | a provider that is already failing stops receiving requests almost immediately |
| Requests not wasted while open | **16 rejected** | the breaker is an action, not a dashboard |
| Recovery after the provider heals | **28.75s** | cooldown plus one successful probe |
| No egress at all | HTTP 200 ×4, all `degraded`, first answer **21.9s**, citations **3/3** | with no route to any provider, the product still answers from its own corpus |
| Air-gap preflight | `GO`, **0 blockers** | the host report you hand the customer |

The most useful number in that table is one that is no longer there. The first
no-egress rehearsal recorded **four non-answers** and each request hung for about
**150 seconds**, because the model client inherited the SDK's defaults: no
timeout, two retries with backoff. A provider that accepted the connection and
then went silent left a citizen waiting two and a half minutes. The client is now
bounded (20s timeout, no retries), which is why that row reads 21.9s — and why
the breaker now opens in 2.32s instead of 122s. A helpdesk answer that takes two
and a half minutes is worse than a degraded answer that takes twenty seconds.

---

## 4. Decisions and the alternatives that were rejected

These are the answers to "why did you do it that way", which is where interviews
are actually won.

**Hybrid retrieval with RRF, not single-index vector search.** Exact scheme
acronyms (`pm-sym`, `pm-kisan`) are precisely where dense embeddings are
weakest, and this user population types acronyms. The lexical channel is cheap;
the fusion is 20 lines. Rejected: reranker by default — 2 GB of RAM on a
free-tier host for a marginal gain on a 4-document context.

**Mechanical quote verification, not an LLM judge.** An LLM judge is another
probabilistic component in the trust path, and it costs a call per answer. Exact
normalized substring matching against the retrieved chunk is deterministic,
free, and explainable to a citizen: either the sentence is in the source file or
it is not. Rejected: "the model was told to cite" — prompt instructions are
not verification.

**Degraded answers instead of canned demo text when the provider fails.** The
old failure path returned a pre-made answer, which is honest but useless — the
customer gets nothing about their question. The new path assembles the most
relevant sentences from the retrieved documents into the same quote format, so
they are *also* machine-verified, and labels the mode. The canned fallback is
retained for the case where retrieval itself is broken. This is the change that
turns "the AI is down" into "the service is in a reduced mode".

**The kill switch is persisted; the circuit breaker is not.** A kill switch that
a redeploy silently undoes is not a kill switch, so it is written atomically to
`OPS_STATE_FILE` (temp file + `os.replace`, so a crash mid-write cannot leave a
half-written file that reads as "enabled"). Breaker state is deliberately
in-memory: a process restart is a fresh chance for a provider, and persisting a
trip would keep refusing calls for no reason.

**The circuit breaker stops calling, it does not just count.** The point is not
dashboards; it is that a provider which is already failing should stop receiving
requests during the cooldown. The counters are split (`provider_failures` versus
`breaker_rejections`) so the second number reads as "requests we did not waste".

**`/health` stays 200 while generation is disabled.** The healthcheck drives the
container lifecycle. If a human pressing the kill switch made `/health` fail,
the orchestrator would restart the container and the switch would look like an
outage. Instead `/health` exposes `ai` and `provider_circuit` for alerting, and
`status` stays `ok`. This is a deliberate separation of *liveness* from *product
state*.

**A rollback restores the environment file too.** The first version restored
only the image, which is the classic incomplete rollback: broken configuration
is a more common cause of a failed release than broken code, and rolling the
binary back while leaving a poisoned `.env` in place leaves the customer still
down. `upgrade.sh` snapshots both; the auto-rollback restores both.

**Deployment pinning lives in its own env file.** The first attempt wrote the
image pin into `.env`, and that broke the app: pydantic-settings rejects unknown
keys by default, so an unrelated variable became a startup crash. Two fixes, and
both were the right ones: the kit writes deployment plumbing to
`state/deploy.env`, and the app now ignores unknown keys, because a customer's
`.env` is not ours alone.

**Scripts are LF-pinned and re-stripped when bundled.** A CRLF shebang on a
Linux host fails with `bad interpreter: ...^M`. `.gitattributes` pins it and
`bundle.sh` strips it anyway on the way out, because the failure mode is a
broken install in front of a customer.

**Preflight has stable codes and severities.** `PF-045` for TLS interception
(blocker, with "install their root CA, never disable verification" as the
remedy), `PF-046` for clock skew measured against the provider's `Date` header,
`PF-040/041` for egress that becomes informational with `--airgap`. The report is
a JSON artifact you hand to the customer, not console output you hope someone
copied.

---

## 5. The five stories FDE interviews are built around

Interviewers for forward-deployed roles ask about judgement, not syntax. Each of
these is answerable from this repository with a real artifact.

**"Tell me about a time you shipped something under a constraint you did not
choose."** The provider's free tier caps at 8k tokens/minute. That shaped the
design: a fast model for normalization and routing, bounded `max_tokens` on
every generation, a semantic cache so paraphrased repeats cost nothing, a
per-IP token bucket, and an eval harness that paces cases to fit the daily
budget. The constraint is documented in the README rather than hidden.

**"A customer's data is nothing like what the product expects."** The corpus is
the example: three provenance classes that cannot be treated alike. Hand-verified
central schemes, state directory seeds, and 2,063 automated portal imports. Each
chunk carries `data_status`, the prompt is instructed never to present a
directory seed as verified eligibility, and `GET /coverage` reports the split so
nobody has to audit the data to learn what trust they are being given.

**"How do you decide when to pull an AI system offline?"** The kill switch, the
circuit breaker, and the escalation ladder in the runbook: rising failures with
the breaker still closed means monitor; breaker open means degraded answers are
live and the customer must be told what they are getting; repeated trips or
schema doubt means stop generation first and discuss second. The mechanism is
`POST /ops/ai`; the judgement is the order of those steps.

**"How do you prove a change is safe on a system you cannot watch?"** The
upgrade path: snapshot the database and the environment, gate on health *and* a
real product call, compare the vector-store row count before and after (a
migration that drops rows passes every health check), and roll back
automatically on failure — rehearsed by shipping a deliberately broken release
in `drill.py` rather than trusting that the rollback works.

**"How do you handle a customer's network policy?"** The preflight doctor exists
because the blockers are never the application: egress policy, a TLS-inspecting
proxy with an untrusted root CA, a clock two minutes off, a port already bound.
In air-gap installs the images travel as verified tarballs with checksums and a
detached signature, and the runtime falls back to retrieval-only answers when no
provider is reachable at all — measured, not assumed.

---

## 6. Weaknesses — say these before you are asked

Say them plainly; they are the difference between a candidate who understands
their system and one who recited a README.

1. **Retrieval quality is measured on 16 curated cases.** It is a regression
   gate, not a benchmark. A real engagement would need a stratified set (by
   language, scheme family, profile constraint) and a held-out split.
2. **No production multi-tenant deployment.** The hosted topology (Vercel + Fly
   + Neon) is documented and the self-hosted path is exercised by the drill, but
   "runs on my machine and in a drill" is not "runs for 10,000 citizens".
3. **A large share of the corpus is unverified portal imports.** The system
   labels it, and does not present it as eligibility advice, but a real
   deployment needs a curation pipeline with an owner.
4. **Single-host Compose is not high availability.** An upgrade has a short
   downtime window while the API container is recreated. Zero-downtime needs a
   different topology; the health gate and rollback logic are the parts that
   carry over.
5. **The provider is a single point of failure.** The gateway override and the
   degraded mode soften it; a second provider with automatic failover is the
   next step, and it is a configuration change plus a routing policy, not a
   rewrite.
6. **The breaker is per-process.** Multiple API replicas would each trip
   independently. Fleet-level would need shared state, and I would argue for
   starting per-process and measuring before adding that complexity.

---

## 7. Questions you will be asked, with answers

**Q: What happens if the LLM returns a quote that is not in the sources?**
The quote line is parsed and verified against the retrieved chunks by normalized
substring match with a tight similarity fallback. It is marked unverified rather
than shown as fact. The verification is deterministic and costs no model call.

**Q: Why hybrid retrieval? What does the lexical channel actually buy?**
Acronyms and exact scheme identifiers. `pm-sym` as a dense vector is noise-adjacent;
as a token match it is exact. RRF fuses the rankings without tuning weights.

**Q: How do you stop the model answering from prior knowledge?**
Three layers: the prompt restricts answers to the provided context and requires
saying so when the context lacks the answer; retrieval supplies a bounded,
source-attributed context; and quotes are verified. It is not a proof of
compliance, which is why the answer also carries its sources with provenance.

**Q: Someone hits the kill switch by mistake. What happens?**
The service keeps answering in degraded mode; nothing goes down; the action is
in the audit trail with actor and reason; re-enabling restores generation. The
worst case is a period of reduced answers, not an outage.

**Q: How do you know the rollback works?**
`drill.py` ships a deliberately broken release and asserts that the upgrade
exits non-zero, that the platform returns to the previous version, and that the
API answers afterwards. A rollback that has never been executed is a plan.

**Q: What would you do on day one of a pilot?**
Preflight the host and hand the customer the JSON report; install from a
verified bundle; run the drill on their staging host so they see the failure
modes; agree the eval slices and the acceptance thresholds in writing; then turn
on the kill switch workflow with their on-call before anyone needs it.

**Q: What does it do when the provider rate-limits?**
Repeated failures trip the breaker, which stops sending requests during the
cooldown and serves retrieval-only answers; one probe decides whether to close.
The counters separate failures from refusals, so the customer can see how many
calls were never wasted.

**Q: Is the data leaving the customer network?**

Retrieved policy excerpts, the question, the fixed system prompt, and — only
when the request attaches a profile — the profile block the caller supplied.
The service renders that block into the prompt (`_build_profile_context` and
`HUMAN_TEMPLATE` in `app/rag.py`), so "the model never sees profile fields"
would be false, and correcting that claim is the first thing I did in my own
engagement packet (`docs/engagement/03-security-packet.md`, section 3). What
does **not** leave: access tokens (accepted by header on the profile endpoints
only, stored as a SHA-256 hash, with no outbound code path able to read them),
profile ids, admin tokens, the corpus and vector store (embedding runs
in-process, `intfloat/multilingual-e5-small`), feedback records, application
logs (exception types and operator actions only, never question or profile
text) and metrics. Retrieval, embeddings and caching are local, so the only
egress is the generation call. With generation disabled — kill switch, breaker
open, or no key — nothing leaves at all and answers still cite retrieved
sources.

The pilot default is to disable profile collection client-side, which takes the
profile store out of the data flow entirely; if a customer wants profiles
enabled, that is their explicit decision, and `display_name` should be left
blank because it is free text and the field most likely to carry a real name.

**Q: Show me something that surprised you.**
The deployment pin in `.env` crashing the app through pydantic-settings'
unknown-key rejection. An unrelated variable took the service down — a config
hygiene bug, not a logic bug, and exactly the class of failure that only shows
up in an environment you do not control. Two fixes: separate the files, and make
the app ignore keys it does not know.

---

## 8. Seven-minute live demo

```bash
docker compose up -d --build
python3 deploy/field/preflight.py --label demo            # codes + verdict
curl -s localhost:8000/ops/status | python3 -m json.tool  # operator surface
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question":"How much does PM-KISAN pay?"}' | python3 -m json.tool
# kill switch on, ask again: same endpoint, mode=degraded, quotes verified
curl -s -X POST localhost:8000/ops/ai -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"enabled": false, "reason": "demo"}'
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question":"PM-KISAN instalments?"}' | python3 -m json.tool
curl -s -X POST localhost:8000/ops/ai -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"enabled": true}'
```

Close on `docs/evidence/FIELD-DRILL.md`: "these are the failure modes, measured
on a real deployment, and here is the command that reproduces them."
