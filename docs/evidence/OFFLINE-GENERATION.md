# Offline generation snapshot — measured results

Frozen evidence for the offline generation regression baseline. It scores the
archived live-run capture in
[`eval/fixtures/generation_snapshot.jsonl`](../../eval/fixtures/generation_snapshot.jsonl)
with only pure `app.quotes` functions: no API key, no database, no network. The
machine-readable output (`eval/results/generation_offline_scores.json`) is
git-ignored, so this document is the committed record.

## Measured result (2026-10-05, this host, over the committed fixture)

Exact command (the provider key is empty on purpose):

```bash
GROQ_API_KEY="" python -m eval.offline_generation
```

Verbatim output:

```text
Offline generation: 8 case(s), quotes=1/2 (verification_rate=0.5), cases_with_citations=2 (citation_coverage=0.25)
Floors passed. Results: eval/results/generation_offline_scores.json
```

| Quantity | Value |
| --- | --- |
| Cases | 8 |
| Cases with a structured quote | 2 |
| Quotes verified (exact substring) | 1/2 |
| Quote verification rate | 0.50 |
| Cases with a citation | 2 |
| Citation coverage | 0.25 |
| Attributed citations | 0/2 |
| Citation attribution rate | 0.00 |
| Quote verification floor | 0.40 |
| Citation coverage floor | 0.20 |

## Fixture provenance

| Field | Value |
| --- | --- |
| Cases | 8 |
| Captured at | `2026-09-01T21:50:00+00:00` |
| Source artifact | `eval/results/scores.json` (archived live-run output) |
| Model | `unknown` (not recoverable from the archive) |
| Corpus generation | `unknown` (not recoverable from the archive) |
| Ids | joined to `eval/questions.json` by exact question text; all 8 matched, so none were derived |
| Sources | the archive's retrieved source metadata, each carrying its chunk `content` |

This is a real live-run capture: on 2026-09-01 the production pipeline
retrieved and generated over the archived cases. The archive's RAGAS score
fields (`faithfulness`, `answer_relevancy`, `context_precision`,
`context_recall`) are all `None` — the judge experiment was retired — and they
are ignored by this evaluation. They are not part of the fixture.

Two limits are stated plainly rather than padded:

- **8 cases is fewer than the 16 in `eval/questions.json`.** The fixture has
  exactly the 8 cases the archive recorded. No case was synthesised,
  extrapolated, or duplicated.
- **Only 1 of the 8 archived cases carried retrieved sources.** The other 7
  recorded a demo fallback in the archive (`error`: "Live RAG returned demo
  fallback"), so they have no sources and their quotes cannot ground. They are
  kept because they are what the real run produced; removing them would
  overstate the capture.

## What the metric does and does NOT claim

**It claims:** each verified quote's text is an exact substring (after
whitespace/punctuation/case normalisation) of a retrieved source chunk for that
case. The offline module proves this without the database by using the source
`content` stored in the fixture.

**It does NOT claim:**

- completeness or factual correctness beyond the quoted text;
- that the model attributed a quote to the right source — the archived capture
  predates the current citation-label contract, so attribution is 0/2 and is
  reported but not gated;
- that the answers are good, only that two folded quote lines were checked and
  one grounded;
- anything about cases the archive did not contain, or about a fresh live run.
- It is a **regression baseline over an archived capture**, not a new live
  measurement, and it is not an ongoing production benchmark.

## Floors

Each floor sits strictly below the first measurement, with the measured value,
the margin, and the reason recorded in the
[`eval/offline_generation.py`](../../eval/offline_generation.py) module
docstring:

| Floor | Value | Measured | Margin | Reason |
| --- | --- | --- | --- | --- |
| Quote verification rate | 0.40 | 0.50 | 0.10 | catches grounding collapsing below the archived capture |
| Citation coverage | 0.20 | 0.25 | 0.05 | catches structured citations disappearing from the pipeline |

A floor breach makes `python -m eval.offline_generation` exit non-zero, which
is how `.github/workflows/offline-generation.yml` fails a pull request that
regresses the archived baseline.

## How to reproduce

```bash
# no key, no database, no network
GROQ_API_KEY="" python -m eval.offline_generation

# regenerate the fixture from the archived artifact (offline)
python scripts/capture_generation_snapshot.py \
  --from-archive eval/results/scores.json \
  --output eval/fixtures/generation_snapshot.jsonl
```
