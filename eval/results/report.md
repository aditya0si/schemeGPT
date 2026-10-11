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
   not reproducible. Fixing the ordering to data-only tie-breaking exposed a
   second defect: the same scheme was indexed twice (verified
   `schemes/pm-kisan.md`, auto-imported `myscheme/pm-kisan.md`) and the top-4
   diversity rule capped one chunk per *source string* rather than per scheme,
   so the deterministic figure fell to **Hit@4 0.8125** / **MRR@4 0.75**, below
   the floor. Capping one chunk per **logical document** and promoting the
   highest-trust copy by `data_status` recovers the verified copy with no case
   regressing. The current measured run completes 16/16 cases with 0 retrieval
   errors at **Hit@4 0.875** and **MRR@4 0.796875**, identical on 5 separate
   runs — above the 0.85 floor. The floor was never lowered. The two
   deterministic misses are the PM-SYM Hinglish and unorganised-worker profile
   questions (no lexical anchor).
2. **Optional live generation experiment** — `python -m eval.run_eval --gate`
   uses the configured Groq model as an explicit JSON judge. The gate passes
   only when every selected case has every metric and there are zero pipeline
   or evaluation errors.

A measured generation baseline should be published here only after a complete
run succeeds. GitHub Actions uploads machine-readable artifacts for both paths.
