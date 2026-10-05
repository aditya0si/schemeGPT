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
| `./.venv/Scripts/python.exe -m pytest -q` | `464 passed, 1 skipped` (465 collected) |
| `./.venv/Scripts/python.exe tools/check_claims.py` | `claims ok: tests=465 evidence=20` |

The binding was driven only by stub callables whose signatures match samjho's
frozen ones, returning `AnswerResult`-shaped pydantic models. The tests assert:
every seam is satisfied (`isinstance` against the `runtime_checkable`
protocols); the four logical names bind, including onto renamed parameters; the
three answer paths survive with `path` intact; a refusal and a degraded result
survive intact; and `citations` / `stripped_citations` map onto the
validated-quote shape. No samjho module was imported at any point.

## What was NOT executed — the honest limit

**samjho's own end-to-end gate was not run.** The plan's Phase 7 goal names
`python -m evals.run_eval --subjects all` over `evals/golden/*.jsonl` and
`evals/refusals.jsonl` as the instrument that proves the mapping. That command
was **not** executed here and **no gate result is claimed**:

- It needs samjho's Postgres with pgvector reachable at `localhost:5432`
  (`api/config.py` defaults `DATABASE_URL` to
  `postgresql://samjho:samjho@localhost:5432/samjho`) plus the ingested
  textbook corpus, neither of which exists in this repository or on this host.
- samjho's repository is outside this workspace boundary; only the read-only
  reference copies staged at `.hermes/ref/samjho/` are available, and they are
  not an installable package.

To actually run it would require, outside this repository: a checkout of samjho
with `api/`, `evals/` and `data/`; a running `pgvector` instance; `python -m
api.db init && python -m api.db load corpus/chunks/*.jsonl`; and then
`python -m evals.run_eval --subjects all`. Until that runs, the adapter is
proven only against signature-faithful stubs, not against samjho's live corpus.

Also **not** executed: samjho's written path against a real provider (the tests
name a stub provider). The database-dependent and network-dependent paths are
out of reach in this environment and nothing about them is asserted.

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
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe tools/check_claims.py
```

The samjho gate itself is **not** reproducible in this environment; see "What
was NOT executed".
