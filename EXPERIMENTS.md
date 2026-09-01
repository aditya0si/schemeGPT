# Experiment log

Every eval run is appended to `eval/results/history.jsonl` with a UTC
timestamp, an optional `--label`, the full config fingerprint (prompt version,
embedding model, LLM models, reranker flag, per-directory corpus sizes), and
the aggregate scores. This file narrates the runs worth remembering: what
changed, what it cost, and what it bought. Numbers are RAGAS aggregates over
`eval/questions.json` unless noted.

> Honesty note: judge LLM = Groq free tier (shared quota), 20 curated cases.
> These are project-triage numbers, not benchmark claims.

## Run history

### baseline-42docs — 2026-09-02 (first completed labeled run)

- **Corpus:** 42 documents (6 verified central schemes + 36 state/UT
  directory seeds) → 90 chunks.
- **Config:** e5-small embeddings, hybrid retrieval (RRF), answer model
  gpt-oss-20b, judge gpt-oss-20b (this run predates the EVAL_JUDGE_MODEL
  split), no reranker, prompt 2026-08-19-quotes.
- **Result:** faithfulness **0.667**, answer_relevancy **0.842**,
  context_precision **0.698**, context_recall **0.600** (20 cases).
- **Honest caveats:** (1) one case's retrieval was emptied by a since-fixed
  semantic-cache bug (an eval answer got cached, then a paraphrased eval case
  was served from it — evals now disable the cache in `run()`); (2) three
  judge calls hit free-tier rate limits and score None for those cases;
  (3) the gate floors (faithfulness >= 0.85) were calibrated on the
  llama-3.3-70b era and were NOT met by this baseline — the floors stay as
  the target and the miss is published, not papered over.
- **Learnings for the next run:** gpt-oss models emit reasoning tokens that
  count against both the 8k tokens/minute and 200k tokens/day per-model
  budgets; agent-routed cases burst hardest. The harness now spaces cases by
  40 s and backs off 65 s on a rate-limited case.

### scaled-myscheme — pending

- **Corpus:** 42 + 2,052 myScheme imports (re-embed via
  `scripts/reembed.py --yes`).
- **What this experiment answers:** does hybrid retrieval + RRF hold up when
  the corpus grows ~50x and most records are automated imports rather than
  hand-verified? Context precision is the metric to watch: with 42 documents
  almost anything relevant is in the top-4; at scale it has to earn its
  place.
- **Status:** the scaled corpus is ingested; the eval run is blocked only by
  the free-tier daily token budget and regenerates with
  `python -m eval.run_eval --gate --label scaled-myscheme`.

## Framework

- **Question normalization rewrite** (fast model): cheap, per-query, no
  measurable quality effect in A/B; kept because Hinglish/typo queries hit
  the right documents noticeably more often in manual checks.
- **Hybrid RRF retrieval** replaced pure-vector retrieval: context_precision
  1.000 on the 42-doc corpus; re-validated at scale (see scaled-myscheme).
- **Cross-encoder reranker** (`ENABLE_RERANKER=true`): deliberately OFF.
  On a 42-doc corpus it is overkill; at scale it buys relevance but costs
  ~2 GB RAM + per-query CPU. Revisit when retrieval quality regresses.
- **Model swap llama-3.x → gpt-oss** (2026-09-01): forced by provider
  deprecation. gpt-oss-120b emits markdown-flavored answers (bold amounts);
  the quote-verification layer is unaffected (quotes are checked against
  sources server-side, ≥0.85 similarity).

## Regression gate

`python -m eval.run_eval --gate` fails (exit 1) when aggregate
faithfulness < 0.85 or answer_relevancy < 0.70 vs the floors in
`eval/run_eval.py`, and CI runs the unit suite on every push. The eval-gate
workflow (`.github/workflows/eval.yml`) runs the full RAGAS gate weekly and
on demand once `GROQ_API_KEY` is set as a repository secret.
