# SchemeGPT Temporal (As-Of) Gate Report

Deterministic, keyless, offline. The as-of answer is a pure function of the committed dated-claims artifact, so every temporal metric is a **consistency floor**, not a quality estimate.

## Provenance

- Golden set: `eval/fixtures/temporal_golden.jsonl` (124 derived cases + 1 artifact-missing probe)
- Artifact: `eval/fixtures/temporal_claims.jsonl` (41 claims, 10 ladders, 2105 documents)
- Generator: `scripts/generate_temporal_golden.py` (regenerate with `./.venv/Scripts/python.exe scripts/generate_temporal_golden.py`)

## Metrics

| Metric | Value | Floor | Verdict |
| --- | ---: | ---: | --- |
| `as_of_accuracy` | 1.000 | 1.000 | pass |
| `boundary_accuracy` | 1.000 | 1.000 | pass |
| `supersession_accuracy` | 1.000 | 1.000 | pass |
| `era_mixing_rate` | 0.000 | 0.000 | pass |
| `refusal_accuracy` | 1.000 | 1.000 | pass |
| `invariance` | n/a | 1.000 | not measured |

## Consistency floors vs quality estimates

- `as_of_accuracy`, `boundary_accuracy`, `supersession_accuracy` and `refusal_accuracy` are **consistency floors**: the answer is a pure function of the frozen artifact, so the honest floor is exactly 1.000. `era_mixing_rate` is a consistency **ceiling** of exactly 0.000.
- There is no quality-estimate metric. The golden set is derived from the same artifact the function reads, so it cannot estimate generalisation to unseen temporal questions; it proves the artifact is obeyed, and the honest value of that proof is exact.
- `invariance` is a consistency floor tied to the retrieval gate's frozen numbers; it is only measured under `--check-default-mode` (which needs the database).

## Case coverage

- Answer-expected: 113; refusal-expected: 12; boundary: 72; supersession: 113; era-mixing denominator: 125

| Kind | Cases |
| --- | ---: |
| `after_last` | 10 |
| `artifact_missing` | 1 |
| `before_first` | 10 |
| `day_before` | 31 |
| `effective_date` | 41 |
| `inside_range` | 31 |
| `unmatched` | 1 |

## Era-mixing definition

A payload is era-mixed when it presents, as the answer for the requested date, a value whose declared effective interval does not contain `as_of`: an answer is era-mixed when the amount in its "*value in force ... is*" clause is not the governing claim's value; a refusal is era-mixed when it presents any in-force amount instead of refusing. An honest refusal of a case that expected an answer is an as-of miss, not an era-mix.

## Invariance

Not measured in this invocation. Run `python -m eval.temporal_gate --check-default-mode` (requires the database) to re-run the retrieval gate and assert its frozen numbers:

- Frozen expectation: 16/16 complete, hit@4 0.875, mrr@4 0.796875

## Gate verdict

**PASSED** -- every measured consistency floor is met.

