# Retrieval gate — measured results

Frozen evidence for the retrieval-quality claim in [`README.md`](../../README.md).
Every number below is a measurement from a real run, not a target. The gate's
machine-readable output (`eval/results/retrieval_scores.json`) is intentionally
git-ignored, so this document and [`eval/results/report.md`](../../eval/results/report.md)
are the committed record.

> **Resolved (2026-10-06): the reproducible figure is back above the Hit@4
> floor — and the floor was never lowered.** The lexical channel used to break
> ties on unspecified Postgres row order, so the previously published 0.875 was
> not reproducible. Making the ordering data-driven exposed a second defect — the
> same scheme indexed twice — and produced **Hit@4 0.8125, MRR@4 0.75**, below
> the 0.85 floor. Keeping the floor fixed and completing the diversity rule
> (one chunk per *logical document*, highest-trust copy wins) recovers the
> verified copy and yields **Hit@4 0.875, MRR@4 0.796875** on every run. See
> "Defect, determinism, and fix" below.

## Defect, determinism, and fix (2026-10-06)

### 1. Plan-dependent lexical tie-break (the determinism defect)

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

This made the gate deterministic and reproducibly exposed the next defect:
**Hit@4 0.8125, MRR@4 0.75**, below the 0.85 floor. The floor was deliberately
not lowered and the fixture was not changed.

### 2. Trust-blind source diversity (the retrieval defect)

**Defect.** The corpus legitimately contains the same scheme twice:
`schemes/pm-kisan.md` (hand-verified, `data_status = sample_verified`) and
`myscheme/pm-kisan.md` (auto-imported, `data_status = myscheme_import`). The
lexical channel's deterministic tie-break is alphabetical on the source path, so
`myscheme/pm-kisan.md` sorts first. `_select_diverse` capped **one chunk per
source string**, which cannot see that the two sources are the same scheme, so
the four provenance slots could be spent on two copies of one scheme and the
verified copy was squeezed out. The `pm-kisan-colloquial` case returned
`myscheme/pm-kisan.md` and missed the labelled `schemes/pm-kisan.md`.

**Fix — one chunk per logical document, best-trust copy wins.**

* The diversity key is now the source **basename** with the extension removed,
  lowercased, and a trailing `(N)` duplicate suffix stripped
  (`app/retrieval.py::_logical_document_key`). So `schemes/pm-kisan.md` and
  `myscheme/pm-kisan.md` share the key `pm-kisan`, while genuinely different
  schemes keep distinct keys.
* When a logical group has more than one member, the representative is the
  highest-trust member by `data_status`: `sample_verified` > `myscheme_import` >
  `directory_seed` > unknown. Ties break on the already-deterministic fused rank
  (the better-ranked member wins). The group occupies the position of its
  best-ranked member, so the verified copy takes the slot the auto-import would
  otherwise have held.
* Unlabelled docs (no `source`) are never grouped — each stays its own document.
* Documented edge cases: two different directories holding different documents
  with the same basename do collapse into one group (accepted; the trust rule
  decides the survivor). A legitimate trailing numeric parenthetical such as
  `report(2024).md` is indistinguishable from a duplicate marker and is stripped
  too; every parenthetical filename in this corpus is a `(1)` duplicate (76
  files, all `(1)`), so the rule matches the real naming convention.

**Why this is correctness, not score tuning.** A system answering questions
about government schemes must cite the hand-verified document in preference to
an automated import of the same scheme. The change implements that rule; the
score is a consequence.

**Regression tests.** `tests/test_retrieval.py` gains
`test_logical_document_key_groups_copies_and_strips_duplicate_suffix`,
`test_final_selection_prefers_verified_copy_of_same_logical_document`,
`test_final_selection_places_group_at_best_ranked_member_position`,
`test_final_selection_follows_documented_trust_precedence`,
`test_final_selection_breaks_trust_ties_on_fused_rank`,
`test_final_selection_is_independent_of_duplicate_row_order`,
`test_final_selection_ignores_which_copy_arrives_first`, and
`test_verified_copy_preferred_regardless_of_fetched_row_order`. The determinism
tests added with fix (1) —
`test_lexical_search_is_independent_of_fetched_row_order` and
`test_generation_sources_returns_a_deterministic_order` — still pass; they fail
against the pre-fix code.

## Measured result (2026-10-06, this host, corpus freshly built)

Exact command:

```bash
python -m eval.retrieval_gate
```

Verbatim output, identical on **5** separate runs (separate processes):

```text
Retrieval evaluation: 16/16 complete, hit@4=0.875, mrr@4=0.796875
```

| Quantity | Value |
| --- | --- |
| Hit@4 | 0.875 |
| MRR@4 | 0.796875 |
| Cases completed | 16/16 |
| Retrieval errors | 0 |
| Hit@4 floor | 0.85 |
| MRR@4 floor | 0.60 |
| Gate | **PASSED** |

### Per-case change versus the 0.8125 baseline

The 13/16 baseline missed `profile-pm-sym`, `pm-sym-hinglish`, and
`pm-kisan-colloquial`. After the fix:

| Case | Before | After |
| --- | --- | --- |
| `pm-kisan-colloquial` | miss | **hit@4 (recovered)** |
| `pm-kisan-exclusions` | hit@2 | hit@1 (rank improved) |
| `profile-pm-sym` | miss | miss (no lexical anchor) |
| `pm-sym-hinglish` | miss | miss (no lexical anchor) |
| other 12 cases | hit | hit (unchanged) |

No case regressed. Hit rate rose 0.8125 → 0.875; MRR@4 rose 0.75 → 0.796875.

## Corpus and configuration

| Field | Value |
| --- | --- |
| Corpus generation | `7213926b8590933d7ae13281f84597695ee8a5df60f8a2b1b133361465a6e689` |
| Chunk count | 26,395 |
| Embedding model | `intfloat/multilingual-e5-small` |
| Retrieval | three-channel hybrid (dense pgvector + Postgres full-text + lexical scheme-name), RRF-fused, logical-document-diverse top-4 |
| Dataset | `eval/questions.json`, 16 source-labelled cases (English, Hindi, Hinglish, profile, jurisdiction) |

The historical 0.875/0.765625 published from CI runs `34847304948` (pull
request) and `34850488645` (main follow-up) was a plan-dependent measurement of
the then-nondeterministic code; its coincidental Hit@4 matches today's
deterministic 0.875, but its MRR@4 (0.765625) does not. The current figure is a
fresh deterministic measurement, not a restoration of that record.

## What is NOT claimed

- This is **not** an ongoing production benchmark. It is one deterministic run
  on one corpus generation and one host on 2026-10-06.
- This is **not** a generation-quality claim. It measures retrieval only; no
  LLM judge is involved.
- This is **not** a claim about other corpora, embedding models, or retrieval
  configurations.
- Retrieval quality is a tracked metric, **not a solved problem**. The two
  remaining deterministic misses are the PM-SYM Hinglish question and the
  unorganised-worker profile question; neither has a lexical anchor in the
  question text.
- The live gate output is not committed; only this frozen record and
  `eval/results/report.md` are.

## How to reproduce

```bash
# database must be running and the corpus ingested
python -m eval.retrieval_gate
```
