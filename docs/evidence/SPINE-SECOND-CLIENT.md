# Second client — samjho attached to the spine

Frozen evidence for Phase 7b: an independently built application attaches to
the six seams in [`app/core/seams.py`](../../app/core/seams.py). This is the
mechanical test of the Phase 7a extraction. The binding lives at
[`clients/samjho/binding.py`](../../clients/samjho/binding.py); samjho's own
modules are read-only reference copies under `.hermes/ref/samjho/` and are never
imported or modified.

## Line count

| File | Lines |
| --- | --- |
| `clients/samjho/binding.py` | **199** (164 non-blank) |
| `clients/samjho/__init__.py` | 5 |
| `clients/__init__.py` | 1 |

The adapter is **199 lines**, under the plan's ~200-line bar. The two
`__init__.py` files are re-export/marker boilerplate, so the whole package is
205 lines; the binding itself is the deliverable and is under the bar.

The length is dominated by two things the client cannot lend the spine:
signature-adaptive binding of the four logical names, and normalising samjho's
pydantic `AnswerResult` into the spine's plain-dict answer payload. The next
finding explains why samjho's own adapter could not be reused for the latter.

## Mapping table

| samjho concept (staged copy) | Spine seam | How the binding maps it |
| --- | --- | --- |
| `api.answer.answer_question(subject, question, chapter_no=None, top_k=None)` returning `AnswerResult` | `Answerer` | Called with the four logical names; the returned model becomes the seam's dict payload (`answer`, `sources`, `mode`). |
| `api.retriever.search(subject, question, chapter_no=None, top_k=None)` | *(no seam)* | Retrieval is inside the answer unit, so the spine has no retrieval seam. Exposed as `SamjhoBinding.retrieve`, not attached to a seam. |
| logical names `question` / `subject` / `chapter_no` / `top_k` | `Answerer` (inputs) | `_bind` maps each logical name onto the parameter spelling the injected callable declares, mirroring `evals/adapter._bind`; unknown required parameters are left for Python to reject loudly. |
| `refused` + `refusal_reason` | `Answerer` (payload) | Passed through unchanged; `path="refusal"`. |
| answer path (`provider` name / `"retrieval-only"` / `refused`) | `Answerer` (`mode` + `path`) | `path` is exact (`written` / `retrieval-only` / `refusal`) and drives `mode`: `written -> "live"`, everything else -> `"degraded"`. |
| `degraded` + `provider` | `Answerer` (payload) | Passed through unchanged, so a provider failure that fell back to retrieval-only stays visible. |
| `citations` (list of `Citation`) | `Answerer` (`sources`) + `Validator` | Citations become spine source dicts tagged with samjho's `[Ch n §s p.p]` label; `Validator` returns records in the `VerifiedQuote` shape (`text`/`source`/`status`/`verified`/`matched_source`). |
| `stripped_citations` (int) | `Answerer` (payload) | Passed through as `stripped_citations`. |
| provider generation | `PolicyGate` / `ModelRouter` | No samjho analogue: the gate defaults to `"ok"` and the router raises a documented `NotImplementedError`. Both are injectable. |
| identifier protection (none in samjho) | `Egress` | Identity over the answer seam; samjho has no vault, so the seam is satisfied but does not redact. |
| *(no streaming surface in samjho)* | `StreamEgress` | The adapter frames the synchronous payload as `sources -> token -> done` SSE blocks. |

## What was executed

| Command | Result |
| --- | --- |
| `./.venv/Scripts/python.exe -m pytest tests/test_samjho_binding.py -q` | `15 passed` |
| `./.venv/Scripts/python.exe -m pytest tests/test_samjho_gate_driver.py -q` | `20 passed` |
| `./.venv/Scripts/python.exe -m pytest -q` | `484 passed, 1 skipped` (485 collected) |
| `./.venv/Scripts/python.exe tools/check_claims.py` | `claims ok: tests=485 evidence=20` |

The binding was driven only by stub callables whose signatures match samjho's
frozen ones, returning `AnswerResult`-shaped pydantic models. The tests assert:
every seam is satisfied (`isinstance` against the `runtime_checkable`
protocols); the four logical names bind, including onto renamed parameters; the
three answer paths survive with `path` intact; a refusal and a degraded result
survive intact; and `citations` / `stripped_citations` map onto the
validated-quote shape. No samjho module was imported at any point.

The Phase 7c driver is tested the same way: its routing is exercised against
signature-faithful stubs (the refusals and degraded results above), its adapter
rebinding is asserted, and its gate exit-code propagation is asserted against a
stand-in runner. No samjho module was imported there either.

## The Phase 7c driver — routing the gate through the spine

`clients/samjho/run_gate_through_spine.py` is the instrument Phase 7c asks for:
it executes **samjho's own** `evals.run_eval` with samjho's own
`evals.adapter.search` / `evals.adapter.answer` rebound to the spine. It imports
samjho lazily (the module itself is stdlib + this repository only) and takes the
frozen `api.answer` / `api.retriever` callables by the attribute names samjho's
own adapter declares, binds them through `bind_samjho(...)`, and normalises the
spine's payload with samjho's own `normalize_answer` / `normalize_hits` so the
shape the harness consumes is unchanged.

Its purpose is the decisive comparison: run samjho's gate **without** the spine
and **with** it, over the same corpus, and compare the table. Identical metrics
mean the spine is behaviour-preserving end-to-end; any difference is a finding
about the binding, not something to hide. The driver therefore also prints a
per-subject routing trace (`searches` / `answers` / `refused` / `degraded` /
`paths`) so a difference can be localised.

**Honesty:** the metrics are samjho's. The driver never recomputes or
reinterprets a score — it only supplies the client responses through the spine
and forwards samjho's gate exit code (`0` pass, `1` fail, `2` cannot run). The
metric table it prints is samjho's own.

The exact orchestration command (run from samjho's checkout root, inside
samjho's venv, with SchemeGPT on `PYTHONPATH`):

```bash
cd C:/Users/oliad/Desktop/samjho
PYTHONPATH="C:/Users/oliad/Desktop/SchemeGPT;C:/Users/oliad/Desktop/samjho" \
    DATABASE_URL="postgresql://samjho:samjho@localhost:5439/samjho" \
    .venv/Scripts/python.exe \
    C:/Users/oliad/Desktop/SchemeGPT/clients/samjho/run_gate_through_spine.py
```

`DATABASE_URL` is the only required override: `api/config.py` defaults to port
5432 while the measured corpus lives on 5439. The orchestrator should compare
the printed table against the **without-spine baseline** measured on the same
1,004-chunk corpus: `hit@4 1.000`, `MRR 0.869`, `page@4 1.000`, `citation hit
0.914`, `golden acceptance 0.971`, `refusal accuracy 0.800` → `GATE PASSED`.

## What was NOT executed — the honest limit

**samjho's own end-to-end gate was not run by the author of these files.** The
Phase 7c driver above exists to run it, but the author is sandboxed to this
repository: samjho's source, venv and database are outside the workspace
boundary, so the driver was only unit-tested against signature-faithful stubs.
**No gate result is claimed here.** The driver is the deliverable; the run is
the orchestrator's, and until it executes, the "what have we proven" question
stays at: the binding maps every concept correctly, but the mapping has not met
samjho's live 1,004-chunk corpus through the spine.

The run is now *possible* outside this repository (the orchestrator reports an
up pgvector instance on port 5439 with the corpus loaded), but it still needs a
samjho checkout with `api/`, `evals/` and `data/`, and it must be launched from
that checkout with `DATABASE_URL` pointed at 5439 (the command is in the Phase
7c section above). `api/config.py` historically defaulted `DATABASE_URL` to
`postgresql://samjho:samjho@localhost:5432/samjho`, which is why the override is
required.

Also **not** executed by the author: samjho's written path against a real
provider (the wiring tests name a stub provider). Nothing about the live
provider path is asserted here.

## Findings

1. **The spine held.** An independent client attaches by supplying six
   callables; the binding imports `app.core.seams` (the contracts), never
   `app.core.scheme` or any SchemeGPT production module for its own behaviour.
2. **The spine's `mode` vocabulary cannot name a refusal.** `mode` is
   `live` / `degraded` / `demo`; a refusal is carried as `mode="degraded"` with
   `refused=True` and the exact source of truth in `path="refusal"`. The spine
   can carry the information, but not in the field the seam defines for it.
3. **`api.retriever.search` has no seam.** Retrieval is subsumed by the answer
   unit, so samjho's second frozen entry point cannot be attached as a seam;
   the binding exposes it beside the spine, not through it. This matches
   Phase 7a's conclusion that only answer / validate / egress are externally
   rebindable.
4. **samjho's existing adapter is lossy for the spine's needs.**
   `evals/adapter.normalize_answer` returns only `refused` / `citations` /
   `refusal_reason` / `provider` / `keys`; it drops `answer`, `degraded` and
   `stripped_citations`. Because this phase requires the degraded result, the
   stripped-citation count and the answer text to survive, the binding
   normalised the raw `AnswerResult` itself. The "reuse the client's adapter"
   premise does not hold for a provenance-preserving attach — which is most of
   the 199 lines.
5. **`gate` / `router` remain SchemeGPT-only.** samjho has no ingress kill
   switch/breaker and no injectable provider router, confirming the Phase 7a
   claim that these two are documented contracts rather than attached seams.

## Reproduce

```bash
./.venv/Scripts/python.exe -m pytest tests/test_samjho_binding.py -q
./.venv/Scripts/python.exe -m pytest tests/test_samjho_gate_driver.py -q
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe tools/check_claims.py
```

The samjho gate itself is **not** reproducible in this repository's
environment; see "What was NOT executed". The Phase 7c section names the
command the orchestrator runs, outside this repository, to make it real.
