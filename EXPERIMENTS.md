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

### baseline-42docs — 2026-09-01

- **Corpus:** 42 documents (6 verified central schemes + 36 state/UT
  directory seeds) → 90 chunks.
- **Config:** e5-small embeddings, hybrid retrieval (RRF), gpt-oss-120b
  answer / gpt-oss-20b normalize, no reranker, prompt 2026-08-19-quotes.
- **Result:** see the table in the README (regenerated from
  `eval/results/report.md`).
- **Notes:** first run after the LLM provider swap (Groq decommissioned the
  Llama-3.x models mid-project; gpt-oss-120b/20b are the replacements). Also
  the first run of the 4-metric harness with a rate-limit-aware judge
  config (RunConfig max_workers=2 — the default parallel executor trips
  Groq's shared token/minute limits and times out).

### scaled-myscheme — 2026-09-01

- **Corpus:** 42 + N myScheme-import records (see `/coverage`) → re-embed via
  `scripts/reembed.py --yes`, then
  `python -m eval.run_eval --gate --label scaled-myscheme`.
- **What this experiment answers:** does hybrid retrieval + RRF hold up when
  the corpus grows ~50x and most records are automated imports rather than
  hand-verified? Context precision is the metric to watch: with 42 documents
  almost anything relevant is in the top-4; at scale it has to earn its place.

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
