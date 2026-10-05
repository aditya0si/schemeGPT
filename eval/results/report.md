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
   current measured run is green: `.github/workflows/eval.yml` run `34847304948`
   (pull request) and its main follow-up `34850488645` completed 16/16 cases
   with 0 retrieval errors at **Hit@4 0.875** and **MRR@4 0.765625** (floors
   unchanged). The two remaining misses are the PM-SYM Hinglish and
   unorganised-worker profile questions, which have no lexical anchor.
2. **Optional live generation experiment** — `python -m eval.run_eval --gate`
   uses the configured Groq model as an explicit JSON judge. The gate passes
   only when every selected case has every metric and there are zero pipeline
   or evaluation errors.

A measured generation baseline should be published here only after a complete
run succeeds. GitHub Actions uploads machine-readable artifacts for both paths.
