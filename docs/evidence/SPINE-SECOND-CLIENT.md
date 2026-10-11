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

The run was launched by the orchestrator from this repository, with samjho on
`PYTHONPATH` so `clients` / `app` resolve from SchemeGPT while `evals` / `api`
resolve from samjho, using samjho's own virtualenv and its live database on port
5439:

```bash
cd C:/Users/oliad/Desktop/SchemeGPT
PYTHONPATH='C:/Users/oliad/Desktop/samjho' \
    DATABASE_URL='postgresql://samjho:<redacted>@localhost:5439/samjho' \
    /c/Users/oliad/Desktop/samjho/.venv/Scripts/python.exe \
    -m clients.samjho.run_gate_through_spine
```

`DATABASE_URL` is the only required override: samjho's `api/config.py` defaults
to port 5432 while the measured corpus lives on 5439. The recorded result is in
the next section.

## The live run — samjho's own gate, through the spine

The orchestrator executed the Phase 7c driver above against samjho's live
database (port 5439, the 1,004-chunk corpus: 593 science + 411 maths). It ran
**samjho's own gate** through the spine binding. The verbatim output was:

```text
[spine] routed evals.adapter.search / evals.adapter.answer through clients.samjho.binding; metrics below are samjho's own

samjho eval gate
  retriever : api.retriever.search(subject: 'str', question: 'str', chapter_no: 'int | None' = None, top_k: 'int | None' = None) -> 'list[RetrievedChunk]'
  answer    : api.answer.answer_question(subject: 'str', question: 'str', chapter_no: 'int | None' = None, top_k: 'int | None' = None) -> 'AnswerResult'
  provider  : retrieval-only
  scope     : chapter   top_k: 6   hit@4 measured on the first 4 of the returned list

subject      n   hit@1   hit@4     MRR  page@4  pgstart  cite_hit  accepted
---------------------------------------------------------------------------
science     20   0.700   1.000   0.833   1.000    0.900     0.900     1.000
maths       15   0.867   1.000   0.917   1.000    0.400     0.933     0.933
ALL         35   0.771   1.000   0.869   1.000    0.686     0.914     0.971

refusals: 15 questions x 2 scope(s) ['science', 'maths'] — judged 15, refused everywhere it could answer: 0.800
          refused with subject=science : 0.933
          refused with subject=maths   : 0.867
          not_course_material : 1.000
          other_board         : 0.500
          out_of_syllabus     : 0.833

metric                measured   threshold   result
------------------------------------------------------
section hit@4            1.000       0.900   PASS
MRR                      0.869       0.750   PASS
page@4                   1.000       0.900   PASS
citation hit             0.914       0.800   PASS
golden acceptance        0.971       0.900   PASS
refusal accuracy         0.800       0.800   PASS

GATE PASSED
[spine] routing trace (diagnostic only; gate metrics are samjho's):
  subject=maths: searches=15 answers=30 refused=14 degraded=0 paths={'retrieval-only': 16, 'refusal': 14}
  subject=science: searches=20 answers=35 refused=14 degraded=0 paths={'retrieval-only': 21, 'refusal': 14}
```

The **without-spine baseline** was measured by the orchestrator on the same
database and the same 1,004-chunk corpus, calling samjho directly:

| metric | without spine | through spine | threshold | result |
| --- | --- | --- | --- | --- |
| section hit@4 | 1.000 | 1.000 | 0.900 | PASS |
| MRR | 0.869 | 0.869 | 0.750 | PASS |
| page@4 | 1.000 | 1.000 | 0.900 | PASS |
| citation hit | 0.914 | 0.914 | 0.800 | PASS |
| golden acceptance | 0.971 | 0.971 | 0.900 | PASS |
| refusal accuracy | 0.800 | 0.800 | 0.800 | PASS |

The per-subject rows are identical too: `science` `0.700 / 1.000 / 0.833 /
1.000 / 0.900 / 0.900 / 1.000` (`hit@1 / hit@4 / MRR / page@4 / pgstart /
cite_hit / accepted`), `maths` `0.867 / 1.000 / 0.917 / 1.000 / 0.400 / 0.933 /
0.933`, and `ALL` `0.771 / 1.000 / 0.869 / 1.000 / 0.686 / 0.914 / 0.971`. The
refusal breakdown is identical (`science` 0.933, `maths` 0.867,
`not_course_material` 1.000, `other_board` 0.500, `out_of_syllabus` 0.833), and
the same three "answered instead of refused" examples, with the same
`below_threshold` reasons, are reported by both runs. Both verdicts are
`GATE PASSED`.

**Conclusion.** Every gated metric, both per-subject rows, the refusal
breakdown and the answered-instead-of-refused examples are IDENTICAL between the
two runs. The Phase 7a extraction is therefore **behaviour-preserving through a
second, independently built client's own full evaluation** — not just through
this repository's signature-faithful stubs.

### Footnotes

* **Key sets differ, and the gate does not score them.** The binding's answer
  payload carries extra source-label keys rather than `AnswerResult`'s exact key
  set. samjho's gate does not score key sets, so "identical" means identical on
  everything the gate measures — no more.
* **No LLM-written path was exercised.** `provider: retrieval-only` means samjho
  answered extractively in this environment (no LLM key was configured), so no
  LLM-written answer path was exercised by either run.
* **This corpus is smaller than samjho's published one.** The measured corpus
  here is 1,004 chunks (science + maths), smaller than the 1,437-chunk database
  samjho's own README reports, so samjho's published figures (hit@4 0.943, MRR
  0.806, refusal 0.867) are **not directly comparable** to these numbers. This
  run neither reproduces nor contradicts samjho's README.
* **Refusal accuracy sits exactly on its threshold.** 0.800 against a 0.800
  floor: it passes, as it did before, but with no margin.

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
6. **The binding is behaviour-preserving end-to-end.** samjho's own gate,
   executed against its live 1,004-chunk corpus through the spine, produced
   metrics identical to the same gate called directly — the mapping is not just
   unit-test-clean, it is score-identical on the client's own evaluation (see
   "The live run" and its footnotes for what "identical" does and does not
   cover).

## Reproduce

```bash
./.venv/Scripts/python.exe -m pytest tests/test_samjho_binding.py -q
./.venv/Scripts/python.exe -m pytest tests/test_samjho_gate_driver.py -q
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe tools/check_claims.py
```

The four commands above reproduce everything in this repository. The samjho
gate itself was run by the orchestrator, from this repository's driver, against
samjho's live database; the exact command and the verbatim output are recorded
in "The live run" above. It is not reproducible from this repository alone
because it needs samjho's checkout, virtualenv and the 1,004-chunk database on
port 5439.
