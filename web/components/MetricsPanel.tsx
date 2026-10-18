import {
  CORPUS,
  EVIDENCE,
  PII,
  RETRIEVAL,
  TEMPORAL,
} from "../lib/measured";

type Metric = {
  id: string;
  label: string;
  value: string;
  detail: string;
  href: string;
  linkLabel: string;
};

const METRICS: Metric[] = [
  {
    id: "retrieval",
    label: "Retrieval gate",
    value: `${RETRIEVAL.hitAt4} Hit@4 · ${RETRIEVAL.mrrAt4} MRR@4`,
    detail:
      `${RETRIEVAL.casesCompleted} source-labelled cases resolved, against floors of ` +
      `${RETRIEVAL.hitAt4Floor} and ${RETRIEVAL.mrrAt4Floor}. Two runtimes are published ` +
      `separately and are never mixed: MRR@4 ${RETRIEVAL.mrrAt4} is the ` +
      `${RETRIEVAL.mrrAt4Runtime} run (fp32 corpus vectors); the same gate on the hosted ` +
      `image's int8 ONNX encoder scored MRR@4 ${RETRIEVAL.mrrAt4Int8} ` +
      `(${RETRIEVAL.mrrAt4Int8Runtime}) on the same corpus and cases. The floors were ` +
      `never lowered for either.`,
    href: EVIDENCE.retrieval,
    linkLabel: "RETRIEVAL-GATE.md",
  },
  {
    id: "temporal",
    label: "Temporal as-of gate",
    value: `as-of ${TEMPORAL.asOf} · boundary ${TEMPORAL.boundary} · supersession ${TEMPORAL.supersession} · refusal ${TEMPORAL.refusal}`,
    detail: `${TEMPORAL.cases} cases derived from ${TEMPORAL.ladders} declared-date ladders, era-mixing rate ${TEMPORAL.eraMixing}. Deterministic, no language model.`,
    href: EVIDENCE.temporal,
    linkLabel: "TEMPORAL-GATE.md",
  },
  {
    id: "pii",
    label: "PII benchmark",
    value: `micro recall ${PII.microRecall} · precision ${PII.microPrecision}`,
    detail:
      "Exact (start, end, kind) span matching over the committed synthetic corpus; no identifier is left unredacted.",
    href: EVIDENCE.pii,
    linkLabel: "PII-BENCHMARK.md",
  },
  {
    id: "corpus",
    label: "Corpus",
    value: `${CORPUS.documents} documents · ${CORPUS.vectors} vectors · ${CORPUS.jurisdictions} jurisdictions`,
    detail:
      "The committed directory seed, verified central samples and portal imports that the retrieval gate measures.",
    href: EVIDENCE.dataOperations,
    linkLabel: "data-operations.md",
  },
];

/**
 * The project's measured results, rendered from `web/lib/measured.ts`.
 *
 * These numbers are the portfolio artifact, so this panel is deliberately
 * *unconditional*: it never depends on whether an API is configured or
 * reachable, and it is the same component on the home page's offline state and
 * on `/evidence`. Every value here is re-derived from a committed evidence
 * document by `tests/test_web_measured_guard.py`.
 */
export function MetricsPanel() {
  return (
    <div data-testid="metrics-panel">
      <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/50">
        Measured results — committed evidence, not estimates
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-px border border-ink/20 bg-ink/20 sm:grid-cols-2">
        {METRICS.map((metric) => (
          <div
            key={metric.id}
            data-testid={`metric-${metric.id}`}
            className="bg-paper p-4"
          >
            <dt className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60">
              {metric.label}
            </dt>
            <dd className="mt-1.5 font-mono text-base font-bold text-ink">
              {metric.value}
            </dd>
            <dd className="mt-2 font-sans text-xs leading-relaxed text-ink/75">
              {metric.detail}
            </dd>
            <a
              href={metric.href}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block font-mono text-[11px] text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
            >
              {metric.linkLabel} ↗
            </a>
          </div>
        ))}
      </dl>

      <div className="mt-4 border-l-4 border-signal bg-paper-dim p-4">
        <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-signal">
          Honest limit
        </p>
        <p className="mt-1 font-sans text-sm leading-relaxed text-ink/85">
          Only {CORPUS.documentsDeclaringADate} of {CORPUS.documents} documents
          declare any effective date, so the as-of capability is real but narrow.
          It is a consistency gate over the dated subset, not a statement about
          the corpus at large.
        </p>
      </div>

      <p className="mt-4 font-mono text-[11px] leading-relaxed text-ink/60">
        Also on the record:{" "}
        <a
          href={EVIDENCE.spine}
          target="_blank"
          rel="noopener noreferrer"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          SPINE-SECOND-CLIENT.md ↗
        </a>{" "}
        ·{" "}
        <a
          href={EVIDENCE.repository}
          target="_blank"
          rel="noopener noreferrer"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          repository root ↗
        </a>
      </p>
    </div>
  );
}
