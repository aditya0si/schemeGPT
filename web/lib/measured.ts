/**
 * Published measurements for the SchemeGPT portfolio demo.
 *
 * This module is the ONE place the frontend reads its published numbers from.
 * Every figure is copied from a committed evidence document; nothing here is
 * rounded, restated, or "improved". If a measurement genuinely changes, change
 * the evidence document first, then this file. `tests/test_web_measured_guard.py`
 * re-derives each value from the document and fails if the two ever disagree.
 *
 * Evidence and the command that reproduces each figure:
 *
 *   Retrieval gate    docs/evidence/RETRIEVAL-GATE.md
 *                     python -m eval.retrieval_gate
 *   Temporal gate     docs/evidence/TEMPORAL-GATE.md
 *                     ./.venv/Scripts/python.exe -m eval.temporal_gate --check-default-mode
 *   PII benchmark     docs/evidence/PII-BENCHMARK.md
 *                     GROQ_API_KEY="" python -m eval.pii_benchmark
 *   Corpus documents  docs/evidence/TEMPORAL-GATE.md
 *   Corpus vectors    docs/evidence/RETRIEVAL-GATE.md
 *   Jurisdictions     docs/data-operations.md
 *   Dated documents   docs/evidence/TEMPORAL-GATE.md
 */

export const RETRIEVAL = {
  casesCompleted: "16/16",
  hitAt4: "0.875",
  mrrAt4: "0.796875",
  hitAt4Floor: "0.85",
  mrrAt4Floor: "0.60",
} as const;

export const TEMPORAL = {
  cases: 124,
  ladders: 10,
  asOf: "1.000",
  boundary: "1.000",
  supersession: "1.000",
  refusal: "1.000",
  eraMixing: "0.000",
} as const;

export const PII = {
  microRecall: "1.000",
  microPrecision: "1.000",
} as const;

export const CORPUS = {
  documents: "2,105",
  vectors: "26,395",
  jurisdictions: 36,
  documentsDeclaringADate: "79",
} as const;

export const EVIDENCE = {
  retrieval:
    "https://github.com/aditya0si/schemeGPT/blob/field-ops-and-deployment-kit/docs/evidence/RETRIEVAL-GATE.md",
  temporal:
    "https://github.com/aditya0si/schemeGPT/blob/field-ops-and-deployment-kit/docs/evidence/TEMPORAL-GATE.md",
  pii: "https://github.com/aditya0si/schemeGPT/blob/field-ops-and-deployment-kit/docs/evidence/PII-BENCHMARK.md",
  spine:
    "https://github.com/aditya0si/schemeGPT/blob/field-ops-and-deployment-kit/docs/evidence/SPINE-SECOND-CLIENT.md",
  dataOperations:
    "https://github.com/aditya0si/schemeGPT/blob/field-ops-and-deployment-kit/docs/data-operations.md",
  repository: "https://github.com/aditya0si/schemeGPT",
} as const;

/** Honest, permanent statement returned when no demo backend is deployed. */
export const OFFLINE_ERROR =
  "This build has no live answering API deployed (no API_URL is configured). " +
  "The application itself is online; the measured results below are the " +
  "project's real, committed numbers, shown so the work can be judged without " +
  "a running backend.";

/** The whole published record, for the offline API response. */
export const PUBLISHED_MEASUREMENTS = {
  retrieval: RETRIEVAL,
  temporal: TEMPORAL,
  pii: PII,
  corpus: CORPUS,
  evidence: EVIDENCE,
} as const;
