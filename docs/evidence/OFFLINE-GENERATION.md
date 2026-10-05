# Offline generation snapshot — measured results

## This is not a generation-quality baseline

This document does **not** establish a generation-quality baseline, and none of
the rates below is a quality signal. The only capture available is degenerate:
**1 of its 8 cases is grounded**, and the other 7 never retrieved a source and
returned a pre-made demo fallback instead. The archive does not record **why**
those 7 fell back, so no cause is asserted here — in particular a rejected
credential must not be inferred. Case 0 is a genuine live answer whose judge
calls were throttled with `RateLimitError` (HTTP 429) *"on tokens per day
(TPD): Limit 200000, Used 199911"*, naming organization
`org_01ks7njm54ehm9mbfdc97rda95`; that proves the credential **authenticated**
on 2026-09-01 and was merely rate-limited. Those 7 cases sit in every
denominator, so the aggregate rates (`quote verification 0.50`,
`citation coverage 0.25`) measure the archive's failure mode, not the
generator. The numbers are published because the mechanism is real and
CI-gated; the quality claim is not.

What the measurement *does* establish is the mechanism: a keyless,
network-free, CI-gated check that a quoted line in an archived answer is an
exact substring of that case's retrieved sources. That mechanism is useful even
though its first input is degenerate, and it is the reason this document
exists.

<!-- offline-provenance: cases=8 grounded_cases=1 quote_lines=2 verified_quotes=1 -->

Frozen evidence for the offline generation regression baseline. It scores the
archived capture in
[`eval/fixtures/generation_snapshot.jsonl`](../../eval/fixtures/generation_snapshot.jsonl)
with only pure `app.quotes` functions: no API key, no database, no network. The
machine-readable output (`eval/results/generation_offline_scores.json`) is
git-ignored, so this document is the committed record. The comment block above
is read by `tests/test_offline_generation.py`, which asserts the stated
provenance counts agree with the fixture and with the module constants
`ARCHIVE_GROUNDED_CASES` / `ARCHIVE_QUOTE_LINES`; the document cannot silently
disagree with the artifact.

## What the archived capture actually contains

The archive is a single run dated `2026-09-01T21:50:00+00:00`. Case by case:

| Case | Id | Sources | Contexts | Quote lines | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | `pmjay-cover` | 4 | 4 | 1 | the only grounded live answer |
| 1 | `gst-launch` | 0 | 0 | 0 | demo fallback |
| 2 | `gst-threshold` | 0 | 0 | 0 | demo fallback |
| 3 | `pm-kisan-payment` | 0 | 0 | 1 | demo fallback (1 stray `>` line) |
| 4 | `pm-kisan-exclusions` | 0 | 0 | 0 | demo fallback |
| 5 | `pm-sym-pension` | 0 | 0 | 0 | demo fallback |
| 6 | `pmay-g-assistance` | 0 | 0 | 0 | demo fallback |
| 7 | `startup-india-eligibility` | 0 | 0 | 0 | demo fallback |

Cases 1–7 all carry the same archive error:

```text
Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating
```

That line is the old harness's own message: it named a credential for *every*
provider failure, so it is not an independent record of the cause. The archive
stores no provider error for cases 1–7, and this document therefore does not
claim one. (Case 0's separate `error` field *does* record a provider error, and
it is a throttle, not a rejection; see below.)

Case 3's lone `>` line is not a generated citation; it is a stray line left
inside a demo-fallback answer, and it is the second of the two quote lines that
the metric folds in. Case 0 is the only case whose answer is absent from the
demo corpus and carries retrieved sources, so it is the only answer that could
ever ground.

### Credential-validity timeline

| Date | Observation | Where |
| --- | --- | --- |
| 2026-09-01 | case 0 carries an authenticated-org throttle: `RateLimitError` HTTP 429 on tokens per day, org `org_01ks7njm54ehm9mbfdc97rda95`, `Used 199911` of `Limit 200000` | `eval/results/scores.json` (case 0 `error`) |
| 2026-10-05 | a read-only models probe with the ambient credential returned `HTTP 401` code `invalid_api_key` | this repository's offline work log |

The credential **authenticated** on 2026-09-01 — it was throttled on the free
tier's daily token cap, not rejected — and it is **invalid** on 2026-10-05. The
change happened somewhere in that roughly five-week window; the exact date is
not recorded in the archive and is not claimed here. Because the archive
records no provider error for the 7 fallbacks, that window is the only
credential statement the evidence supports.

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

Every row below states its denominator. The denominator includes the 7 demo
fallbacks, which have no sources and therefore cannot ground a quote; rows that
are not a quality signal say so directly.

| Quantity | Value | Denominator | Basis / caveat |
| --- | --- | --- | --- |
| Cases | 8 | — | 1 grounded + 7 demo fallbacks |
| Cases with a structured quote | 2 | of 8 cases | 1 real (case 0) + 1 stray `>` line in a demo fallback (case 3); **not a quality signal** |
| Quotes verified (exact substring) | 1/2 | of 2 quote lines | the denominator counts the stray demo-fallback line; **not a quality signal** |
| Quote verification rate | 0.50 | 2 quote lines (1 real, 1 demo-fallback stray) | **not a quality signal** |
| Cases with a citation | 2 | of 8 cases | denominator includes 7 demo fallbacks; **not a quality signal** |
| Citation coverage | 0.25 | 8 cases, 7 of them demo fallbacks that cannot cite | **not a quality signal** |
| Attributed citations | 0/2 | of 2 quote lines | 0 because the archive predates the current citation-label contract |
| Citation attribution rate | 0.00 | 2 quote lines | reported, not gated |
| Quote verification floor (PROVISIONAL) | 0.40 | — | derived from the degenerate 0.50 measurement |
| Citation coverage floor (PROVISIONAL) | 0.20 | — | derived from the degenerate 0.25 measurement |

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

The archive is a single real run, but it is a degenerate capture: only case 0
was answered live; the other 7 are demo fallbacks recorded by the same run. The
archive does not record the cause of those 7 fallbacks. It is not "the
production pipeline retrieved and generated over all the archived cases".

The archive's RAGAS score fields (`faithfulness`, `answer_relevancy`,
`context_precision`, `context_recall`) are all `None` — the judge experiment
was retired — and they are ignored by this evaluation. They are not part of the
fixture.

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

## Floors — PROVISIONAL

Both floors are **PROVISIONAL**. They were derived from a degenerate first
measurement (7 of 8 cases had no sources and could not ground a quote) and must
be re-derived after the first **valid** capture. A capture is valid when:

- every case carries at least one retrieved source, and
- no case carries the demo-fallback error (the run used a working credential),
  and
- the archive's `generated_at` is later than 2026-10-05.

Each floor sits strictly below that first measurement, with the measured value,
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

## Re-capture protocol

1. Supply a valid `GROQ_API_KEY` to the live harness (never commit it).
2. Produce an archive over all 16 questions with no demo fallbacks and no
   pipeline errors:
   ```bash
   python -m eval.run_eval --limit 16
   ```
3. Rebuild the fixture from that archive:
   ```bash
   python scripts/capture_generation_snapshot.py \
     --from-archive eval/results/scores.json \
     --output eval/fixtures/generation_snapshot.jsonl
   ```
4. Re-run the offline metric and read the new numbers:
   ```bash
   GROQ_API_KEY="" python -m eval.offline_generation
   ```
5. **Update the floors and this document together, in the same commit.** A
   floor or a stated provenance count that changes without the other is a
   drift: `tests/test_offline_generation.py` pins the stated provenance counts
   to the fixture, and `tools/evidence_manifest.py` pins the document's bytes
   to the manifest.
6. Rebaseline the manifest in that same commit:
   ```bash
   python tools/evidence_manifest.py --write
   ```

## How to reproduce

```bash
# no key, no database, no network
GROQ_API_KEY="" python -m eval.offline_generation

# regenerate the fixture from the archived artifact (offline)
python scripts/capture_generation_snapshot.py \
  --from-archive eval/results/scores.json \
  --output eval/fixtures/generation_snapshot.jsonl
```
