import {
  CORPUS,
  EVIDENCE,
  OFFLINE_ERROR,
  PII,
  RETRIEVAL,
  TEMPORAL,
} from "../lib/measured";

type Metric = {
  label: string;
  value: string;
  detail: string;
  href: string;
  linkLabel: string;
};

const METRICS: Metric[] = [
  {
    label: "Retrieval gate",
    value: `${RETRIEVAL.hitAt4} Hit@4 · ${RETRIEVAL.mrrAt4} MRR@4`,
    detail: `${RETRIEVAL.casesCompleted} source-labelled cases resolved, against floors of ${RETRIEVAL.hitAt4Floor} and ${RETRIEVAL.mrrAt4Floor}.`,
    href: EVIDENCE.retrieval,
    linkLabel: "RETRIEVAL-GATE.md",
  },
  {
    label: "Temporal as-of gate",
    value: `as-of ${TEMPORAL.asOf} · boundary ${TEMPORAL.boundary} · supersession ${TEMPORAL.supersession} · refusal ${TEMPORAL.refusal}`,
    detail: `${TEMPORAL.cases} cases derived from ${TEMPORAL.ladders} declared-date ladders, era-mixing rate ${TEMPORAL.eraMixing}. Deterministic, no language model.`,
    href: EVIDENCE.temporal,
    linkLabel: "TEMPORAL-GATE.md",
  },
  {
    label: "PII benchmark",
    value: `micro recall ${PII.microRecall} · precision ${PII.microPrecision}`,
    detail:
      "Exact (start, end, kind) span matching over the committed synthetic corpus; no identifier is left unredacted.",
    href: EVIDENCE.pii,
    linkLabel: "PII-BENCHMARK.md",
  },
  {
    label: "Corpus",
    value: `${CORPUS.documents} documents · ${CORPUS.vectors} vectors · ${CORPUS.jurisdictions} jurisdictions`,
    detail:
      "The committed directory seed, verified central samples and portal imports that the retrieval gate measures.",
    href: EVIDENCE.dataOperations,
    linkLabel: "data-operations.md",
  },
];

export function OfflinePanel() {
  return (
    <section
      data-testid="offline-panel"
      aria-label="Offline demonstration"
      className="border-2 border-ink bg-paper p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/20 pb-3">
        <span className="font-mono text-[11px] font-bold uppercase tracking-wider text-ink">
          Status · live API not deployed
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink/60">
          Deliberate offline state — not an error
        </span>
      </div>

      <h2 className="mt-4 font-sans text-2xl font-bold uppercase leading-tight tracking-tight text-ink">
        The live answering API is not deployed.
      </h2>
      <p className="mt-3 max-w-2xl font-sans text-sm leading-relaxed text-ink/85">
        {OFFLINE_ERROR}
      </p>

      <p className="mt-5 font-mono text-[10px] font-bold uppercase tracking-wider text-ink/50">
        Measured results — committed evidence, not estimates
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-px border border-ink/20 bg-ink/20 sm:grid-cols-2">
        {METRICS.map((metric) => (
          <div key={metric.label} className="bg-paper p-4">
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
              className="mt-2 inline-block font-mono text-[11px] text-linkblue underline hover:opacity-80"
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
          className="text-linkblue underline hover:opacity-80"
        >
          SPINE-SECOND-CLIENT.md ↗
        </a>{" "}
        ·{" "}
        <a
          href={EVIDENCE.repository}
          target="_blank"
          rel="noopener noreferrer"
          className="text-linkblue underline hover:opacity-80"
        >
          repository root ↗
        </a>
      </p>
    </section>
  );
}
