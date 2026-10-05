# PII recognizers — measured recall / precision

Frozen evidence for the Phase 6a detection core
([`app/guardrails/recognizers.py`](../../app/guardrails/recognizers.py)). Every
number below is a measurement from a real run against the committed synthetic
corpus, not a target. The machine-readable output
(`eval/results/pii_benchmark.json`) is git-ignored, so this document is the
committed record. The comment block below is read by
`tests/test_pii_benchmark.py`, which asserts the stated provenance agrees with
the committed corpus; the document cannot silently drift from the artifact.

<!-- pii-provenance: seed=20261005 records=30 labelled_spans=25 negative_records=8 -->

## Measured result (2026-10-05, this host, over the committed corpus)

Exact command (the provider key is empty on purpose; the benchmark needs no key):

```bash
GROQ_API_KEY="" python -m eval.pii_benchmark
```

Verbatim output:

```text
PII benchmark: 30 record(s), micro recall=1.000 precision=1.000, macro recall=1.000 precision=1.000, negatives=8 (0 matched)
Floors passed. Results: eval/results/pii_benchmark.json
```

A prediction counts as a true positive **only when its `(start, end, kind)`
triple equals a labelled span exactly**. A prediction that covers the same
characters under a different `kind`, or any prediction on a negative record, is
a false positive for its kind and a false negative for the labelled kind.

| Kind | Labels | Predictions | True pos. | False pos. | False neg. | Recall | Precision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `aadhaar` | 5 | 5 | 5 | 0 | 0 | 1.000 | 1.000 |
| `devanagari_digits` | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| `gstin` | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| `ifsc` | 2 | 2 | 2 | 0 | 0 | 1.000 | 1.000 |
| `mobile` | 6 | 6 | 6 | 0 | 0 | 1.000 | 1.000 |
| `pan` | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| `upi` | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| **micro** | **25** | **25** | **25** | **0** | **0** | **1.000** | **1.000** |
| **macro** | — | — | — | — | — | **1.000** | **1.000** |

Micro aggregates every true positive, label and prediction. Macro is the
unweighted mean of the per-kind rates. Eight negative records carried no labels
and **none** produced a match.

### Case handling (re-measured 2026-10-05)

PAN, GSTIN, and IFSC now match case-insensitively; UPI already did (its local
part and handle accept either case), and the numeric kinds -- Aadhaar, mobile,
and the Devanagari-digit run -- have no case. The change is an egress fix, not a
cosmetic one: a citizen who types a PAN in lowercase (`mljmi4203y`) must still
have it redacted, because an unrecognised identifier is an identifier that
leaves the box. The reported span is always the **original** text the user
typed, never an uppercased normalisation, so redaction replaces exactly the
matched characters. No identifier kind is left case-sensitive.

Re-measurement after the change, over the same committed corpus, is **unchanged
in every cell above**: the corpus is generated in uppercase, so the case
decision moves no published number. The decision is recorded here because a
number that does *not* move under a matching change is itself worth stating.
Case-insensitive matching only widens character classes; it cannot manufacture
five consecutive letters where none exist, so the near-miss negatives
(`neg-high-entropy`, `neg-pan-malformed`, the non-mobile prefixes) are
unaffected. The behaviour is pinned in `tests/test_guardrails_recognizers.py`:
lowercase PAN/GSTIN/IFSC match and report the original span, and a lowercase
alternating high-entropy token does not fire.

## Corpus provenance

| Field | Value |
| --- | --- |
| Generator | `scripts/generate_synthetic_pii_corpus.py` |
| Seed | `20261005` |
| Records | 30 (22 with labels, 8 negatives) |
| Labelled spans | 25 |
| Kinds | `aadhaar` 5, `devanagari_digits` 3, `gstin` 3, `ifsc` 2, `mobile` 6, `pan` 3, `upi` 3 |
| Languages | English, Hinglish (Roman-script Hindi), Devanagari script |
| Generated | 2026-10-05 (no timestamp is stored in the corpus, so it is byte-stable) |

The corpus is **entirely synthetic**. Values are drawn from a seeded
`random.Random`; a valid Aadhaar is an 11-digit payload plus a Verhoeff check
digit, and no real person's identifier is generated, emitted, or committed. A
positive label is only ever placed on a value that genuinely satisfies the
relevant structure (Verhoeff for Aadhaar, the PAN/GSTIN/IFSC/UPI/mobile shape
otherwise).

### The labels are independent of the recognizers

The generator builds each sentence by concatenating literals and known-good
values and records the labelled span at construction time (`start = len(prefix)`)
— it never scans the sentence with a recognizer. The generator module does not
import `app.guardrails` at all; this is asserted in
`tests/test_pii_benchmark.py`. The generator also carries its **own,
independent** Verhoeff implementation, so a defect in the recognizer's
checksum cannot be masked by the corpus sharing it. The concentrated test for
this: every positively-labelled Aadhaar is re-validated by the recognizer's
Verhoeff in the test suite, and the classic external example (`2363` valid,
`2364` invalid) is checked separately.

### How the negatives were produced

Eight records carry no labels and must not match:

| Negative id | Construction | Why it must not match |
| --- | --- | --- |
| `neg-aadhaar-verhoeff` | 12 digits whose check digit was advanced by one | valid shape, failing Verhoeff |
| `neg-pan-malformed` | four leading letters, not five | not a PAN |
| `neg-non-mobile-zero` / `neg-non-mobile-five` | ten digits starting 0–5 | not a 6–9 mobile prefix |
| `neg-high-entropy` | alternating letter/digit token, length 13 | can never contain five consecutive letters, so it is no identifier fragment |
| `neg-aadhaar-in-run` | a valid Aadhaar embedded between two digits | a 12-digit span inside a longer run is not a standalone Aadhaar |
| `neg-eleven-digit` | an 11-digit code | not any supported kind |
| `neg-email` | `field.ops@example.com` | a dotted email domain is not a UPI id |

Every negative was chosen so that the correct answer is "no match". They are
what makes the precision figure mean anything.

## Floors

The floors sit strictly below the first measurement, leaving room for benign
drift while still failing on a real regression. They are regression tripwires,
not targets.

| Gate | Floor | Measured | Margin | Reason |
| --- | --- | --- | --- | --- |
| Micro recall | 0.92 | 1.000 | 0.08 | a wording change should not be able to hide more than one or two spans |
| Micro precision | 0.92 | 1.000 | 0.08 | one stray match on a negative must not sink the gate, a systematic one must |
| Macro recall | 0.90 | 1.000 | 0.10 | macro weights a rare kind equally, so it is given slightly more slack |
| Macro precision | 0.90 | 1.000 | 0.10 | as above for precision |
| Minimum negative records | 5 | 8 | — | precision is meaningless without near-misses; dropping them fails the gate |

A floor breach makes `python -m eval.pii_benchmark` exit non-zero, which is how
`.github/workflows/pii-benchmark.yml` fails a pull request that regresses recall
or precision.

## What this measures — and what it does not

**It measures** the recognizers' behaviour on a corpus generated by the same
author from a fixed seed. That is a **self-consistency and regression check**:
it proves the recognizers still recover the identifier shapes they were written
for, on English, Hinglish, and Devanagari-digit text, and that they do not fire
on the deliberate near-misses.

**It does not measure** real-world PII recall or precision on messy human text.
Because the corpus is synthetic and built from known-good values by the same
author as the recognizers, a perfect score means the contract is internally
consistent — **not** that the detectors will find identifiers in the wild, where
formatting, transliteration, OCR noise, and adversarial obfuscation vary far
beyond this fixture. The number is a regression signal to be defended, not a
field result to be quoted.

Additional explicit limits:

- The corpus is small (30 records, 25 spans) and deliberately clean; it is not a
  statistical sample of Indian text.
- It covers seven identifier kinds only. Addresses, names, dates of birth, and
  other quasi-identifiers are out of scope.
- PAN, GSTIN, IFSC, and UPI match case-insensitively (see "Case handling"); the
  numeric kinds have no case. Nothing is left case-sensitive on purpose, so there
  is no deliberate case gap to state.
- This benchmark measures detection only. The request-path integration and its
  own tests are the separate Phase 6b section below; streaming overlap buffering
  is Phase 6c.

## Request-path integration (Phase 6b)

Phase 6b wires the detection core into the **non-streaming** `POST /query` path.
Streaming is Phase 6c and is untouched.

- **What is redacted.** The inbound question, before retrieval or generation.
  Each detected span is replaced with a request-scoped placeholder
  (`[[PII:<nonce>:<KIND>:<n>]]`) from `app.guardrails.vault.Vault`. The raw
  identifier is exactly what would otherwise have left the process in the prompt
  to the hosted provider; the placeholder is not reversible without that
  request's in-memory mapping.
- **When.** On every synchronous question, if `ENABLE_PII_VAULT` is on and at
  least one identifier is detected. The outbound answer is restored
  (placeholders back to originals) before it is returned. A question with no
  detected PII is passed through byte-identically, semantic cache included.
- **Cache.** A request that contained PII **bypasses the semantic cache
  entirely** — both the lookup and the store. This is deliberate: an answer
  containing a restored identifier must never be written where a different
  request could later be served it. Clean questions still use the cache
  normally.
- **Config default.** `ENABLE_PII_VAULT=true` (see `app/config.py`): redaction is
  **on by default**. `ENABLE_PII_VAULT=false` is a documented escape hatch that
  restores the pre-6b behaviour.
- **Mapping handling.** The mapping lives only on the stack of one call: it is
  never logged, persisted, cached, or placed in a response field, and
  `Vault.__repr__` is opaque so an accidental log of the object cannot spill the
  originals.

### How the egress guarantee is proven

The egress guarantee is proven **against a stubbed provider client in tests, not
by inspecting real network traffic**. `tests/test_guardrails_middleware.py`
drives a synthetic, checksum-valid Aadhaar through the real `app.rag.answer`
pipeline with a fake provider client that records every prompt it is handed.
The test then asserts the captured payload contains no Aadhaar-shaped string
(`find_all(payload) == []`) and no raw value, while the citizen-facing answer has
the original restored. The same suite proves cross-request isolation (two
requests with the same identifier do not share a mapping), that a PII request
bypasses the cache, and that a second request cannot be served the first
request's identifier. The guarantee is therefore bounded by what the code sends
to the provider client; no real socket is observed.

Known limitation: only the question is scanned. Free-text profile fields
(`occupation`, `goals`) are not redacted in 6b.

## How to reproduce

```bash
# regenerate the corpus (byte-stable for the fixed seed)
python scripts/generate_synthetic_pii_corpus.py

# score it with no key, no database, no network
GROQ_API_KEY="" python -m eval.pii_benchmark
```
