# SchemeGPT Generation Evaluation Report

**Status: no valid current generation baseline.**

The previously tracked RAGAS report was incomplete: different metrics covered
different subsets of the selected cases because provider quota failures were
recorded as missing scores. It was therefore not a defensible aggregate and has
been retired rather than presented as evidence.

Current evaluation is split into two paths:

1. **Required deterministic retrieval gate** — `python -m eval.retrieval_gate`
   evaluates all 16 source-labelled cases against the full ingested corpus
   generation `7213926b8590933d...` (2,105 markdown files, ~20k chunks) and
   fails on any missing/error case, Hit@4 below 0.85, or MRR@4 below 0.60. The
   gate was found to be plan-dependent — the lexical channel broke ties on
   unspecified Postgres row order — so the earlier published 0.875/0.765625 was
   not reproducible (0.8125 ↔ 0.875). After fixing the ordering to data-only
   tie-breaking, the current measured run completes 16/16 cases with 0
   retrieval errors at **Hit@4 0.8125** and **MRR@4 0.75**, identical on 5
   separate runs. That is below the 0.85 floor, so the gate **currently fails**;
   the floor was not lowered. The deterministic misses are the PM-SYM Hinglish
   and unorganised-worker profile questions (no lexical anchor) plus the
   PM-KISAN colloquial question. Raising retrieval quality is a separate task.
2. **Optional live generation experiment** — `python -m eval.run_eval --gate`
   uses the configured Groq model as an explicit JSON judge. The gate passes
   only when every selected case has every metric and there are zero pipeline
   or evaluation errors.

A measured generation baseline should be published here only after a complete
run succeeds. GitHub Actions uploads machine-readable artifacts for both paths.
