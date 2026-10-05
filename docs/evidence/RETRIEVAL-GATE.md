# Retrieval gate — measured results

Frozen evidence for the published retrieval-quality claim in [`README.md`](../../README.md).
Every number below is a measurement from a real run, not a target. The gate's
machine-readable output (`eval/results/retrieval_scores.json`) is intentionally
git-ignored, so this document and [`eval/results/report.md`](../../eval/results/report.md)
are the committed record.

## Measured result (2026-10-05, this host, post-merge, corpus freshly built)

Exact command:

```bash
python -m eval.retrieval_gate
```

Verbatim output:

```text
Retrieval evaluation: 16/16 complete, hit@4=0.875, mrr@4=0.765625
Gate passed. Results: eval/results/retrieval_scores.json
```

| Quantity | Value |
| --- | --- |
| Hit@4 | 0.875 |
| MRR@4 | 0.765625 |
| Cases completed | 16/16 |
| Retrieval errors | 0 |
| Hit@4 floor | 0.85 |
| MRR@4 floor | 0.60 |

## Corpus and configuration

| Field | Value |
| --- | --- |
| Corpus generation | `scheme_docs_v2` |
| Chunk count | 26,395 |
| Embedding model | `intfloat/multilingual-e5-small` |
| Retrieval | three-channel hybrid (dense pgvector + Postgres full-text + lexical scheme-name), RRF-fused, source-diverse top-4 |
| Dataset | `eval/questions.json`, 16 source-labelled cases (English, Hindi, Hinglish, profile, jurisdiction) |

The same figures are the ones attributed in the README to CI runs
`34847304948` (pull request) and `34850488645` (main follow-up) on corpus
generation `7213926b8590933d...`. The re-measurement above was taken on this
host on 2026-10-05 after the Phase 0 merge and Windows event-loop fix, against a
freshly built corpus; no published figure was changed.

## What is NOT claimed

- This is **not** an ongoing production benchmark. It is one deterministic run
  on one corpus generation and one host on 2026-10-05.
- This is **not** a generation-quality claim. It measures retrieval only; no
  LLM judge is involved.
- This is **not** a claim about other corpora, embedding models, or retrieval
  configurations.
- Retrieval quality is a tracked metric, **not a solved problem**. The two
  remaining misses are the PM-SYM Hinglish question and the unorganised-worker
  profile question, which have no lexical anchor.
- The live gate output is not committed; only this frozen record and
  `eval/results/report.md` are.

## How to reproduce

```bash
# database must be running and the corpus ingested
python -m eval.retrieval_gate
```
