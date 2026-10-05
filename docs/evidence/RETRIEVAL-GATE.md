# Retrieval gate — measured results

Frozen evidence for the retrieval-quality claim in [`README.md`](../../README.md).
Every number below is a measurement from a real run, not a target. The gate's
machine-readable output (`eval/results/retrieval_scores.json`) is intentionally
git-ignored, so this document and [`eval/results/report.md`](../../eval/results/report.md)
are the committed record.

> **Open finding (2026-10-06): the reproducible figure is below the Hit@4
> floor.** The lexical channel used to break ties on unspecified Postgres row
> order, so the previously published 0.875 was not reproducible. After making
> the ordering data-driven, the same command returns **Hit@4 0.8125, MRR@4
> 0.75** on every run — **below the 0.85 floor**, so the gate now **FAILS**. The
> floor was deliberately not lowered, the fixture was not changed, and raising
> retrieval quality is a separate, later task. See "Defect and fix" below.

## Defect and fix (2026-10-06)

**Defect.** `app/retrieval.py::_lexical_search` broke ties between chunks with
each row's position in the result of `_fetch_source_chunks`. That query had no
`ORDER BY`, so its row order was unspecified. The affected case is a near-tie
between the hand-verified `schemes/pm-kisan.md` (the labelled expectation) and
the auto-imported `myscheme/pm-kisan.md`: both contain a chunk 0 with the same
token-overlap count, so the winner was whichever row Postgres happened to return
first. One chunk per source survives de-duplication, so the choice propagated
through `rrf_fuse` and `_select_diverse`, and the gate score moved between runs
on an identical corpus.

**Observed plan dependence.** Before the fix, `python -m eval.retrieval_gate` on
corpus generation `7213926b8590933d...` (26,395 chunks, one generation,
`intfloat/multilingual-e5-small`, exact dense scan, `enable_reranker=False`, no
code change) returned both:

```text
hit@4=0.8125, mrr@4=0.75
hit@4=0.875, mrr@4=0.765625
```

A gate that can answer either value for the same input cannot distinguish a real
retrieval regression from a re-plan.

**Fix.**

* `_fetch_source_chunks` now ends with
  `ORDER BY metadata->>'source', metadata->>'chunk_index', content`, so the SQL
  result has a defined order.
* `_lexical_search`'s sort key no longer contains the fetched-row position. It is
  `(-token_hits, chunk_index, metadata->>'source', md5(content))` — data only,
  ending on a stable identifier.
* `_generation_sources` now runs `SELECT DISTINCT ... ORDER BY source` and also
  returns its values sorted in Python, as defence in depth.

**Regression tests.** `tests/test_retrieval.py::test_lexical_search_is_independent_of_fetched_row_order`
serves the same rows in reverse and asserts the ranked source order is
unchanged; `tests/test_retrieval.py::test_generation_sources_returns_a_deterministic_order`
pins the distinct-source order. Both fail against the pre-fix code.

## Measured result (2026-10-06, this host, corpus freshly built)

Exact command:

```bash
python -m eval.retrieval_gate
```

Verbatim output, identical on **5** separate runs (separate processes):

```text
Retrieval evaluation: 16/16 complete, hit@4=0.8125, mrr@4=0.75
GATE FAILED: hit_rate_at_k: 0.812 < 0.85
```

| Quantity | Value |
| --- | --- |
| Hit@4 | 0.8125 |
| MRR@4 | 0.75 |
| Cases completed | 16/16 |
| Retrieval errors | 0 |
| Hit@4 floor | 0.85 |
| MRR@4 floor | 0.60 |
| Gate | **FAILED** (Hit@4 below floor) |

## Corpus and configuration

| Field | Value |
| --- | --- |
| Corpus generation | `7213926b8590933d7ae13281f84597695ee8a5df60f8a2b1b133361465a6e689` |
| Chunk count | 26,395 |
| Embedding model | `intfloat/multilingual-e5-small` |
| Retrieval | three-channel hybrid (dense pgvector + Postgres full-text + lexical scheme-name), RRF-fused, source-diverse top-4 |
| Dataset | `eval/questions.json`, 16 source-labelled cases (English, Hindi, Hinglish, profile, jurisdiction) |

The previously published 0.875/0.765625 was attributed to CI runs `34847304948`
(pull request) and `34850488645` (main follow-up) on this same corpus
generation. Those runs are historical measurements of the then-nondeterministic
code; the figure they reported is no longer reproducible and has been corrected
rather than preserved.

## What is NOT claimed

- This is **not** an ongoing production benchmark. It is one deterministic run
  on one corpus generation and one host on 2026-10-06.
- This is **not** a generation-quality claim. It measures retrieval only; no
  LLM judge is involved.
- This is **not** a claim about other corpora, embedding models, or retrieval
  configurations.
- Retrieval quality is a tracked metric, **not a solved problem**. The three
  deterministic misses are the PM-SYM Hinglish question, the unorganised-worker
  profile question (neither has a lexical anchor), and the PM-KISAN colloquial
  question, where the auto-imported `myscheme/pm-kisan.md` now deterministically
  outranks the hand-verified `schemes/pm-kisan.md`.
- The live gate output is not committed; only this frozen record and
  `eval/results/report.md` are.

## How to reproduce

```bash
# database must be running and the corpus ingested
python -m eval.retrieval_gate
```
