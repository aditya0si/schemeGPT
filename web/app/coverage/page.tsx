import { CORPUS } from "../../lib/measured";

export const dynamic = "force-dynamic";

type Jurisdiction = {
  name?: string | null;
  code?: string | null;
  type?: string | null;
  data_status?: string | null;
  catalog_record_count?: number | null;
};

type CoverageReport = {
  jurisdiction_count?: number | null;
  state_count?: number | null;
  union_territory_count?: number | null;
  catalog_records_total?: number | null;
  catalog_sample_verified_count?: number | null;
  catalog_directory_seed_count?: number | null;
  catalog_by_status?: Record<string, number> | null;
  per_jurisdiction?: Jurisdiction[] | null;
  coverage_note?: string | null;
};

type CoverageState =
  | { kind: "unconfigured" }
  | { kind: "unavailable"; reason: string }
  | { kind: "report"; report: CoverageReport };

const TIMEOUT_MS = 4000;

async function getCoverage(apiUrl: string | null): Promise<CoverageState> {
  if (!apiUrl) return { kind: "unconfigured" };
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const res = await fetch(`${apiUrl}/coverage`, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timer);
    if (!res.ok) {
      return { kind: "unavailable", reason: `the API answered HTTP ${res.status}` };
    }
    return { kind: "report", report: (await res.json()) as CoverageReport };
  } catch (error) {
    const aborted = (error as Error).name === "AbortError";
    return {
      kind: "unavailable",
      reason: aborted
        ? `the API did not answer within ${TIMEOUT_MS / 1000}s (a free-tier instance may be waking up)`
        : "the API could not be reached",
    };
  }
}

function StatusBreakdown({ byStatus }: { byStatus: Record<string, number> }) {
  const entries = Object.entries(byStatus).sort((a, b) => b[1] - a[1]);
  return (
    <dl className="mt-3 grid grid-cols-1 gap-px border border-ink/20 bg-ink/20 sm:grid-cols-3">
      {entries.map(([status, count]) => (
        <div key={status} className="bg-paper p-3">
          <dt className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60">
            {status}
          </dt>
          <dd className="mt-1 font-mono text-lg font-bold text-ink">{count}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * /coverage — what the corpus actually contains, straight from `GET /coverage`.
 *
 * Three explicitly labelled states, never a silent blank: no API configured, API
 * configured but unavailable (with the reason and where the same numbers are
 * committed), and a live report with the API's own `coverage_note` reproduced
 * verbatim. This page adds no new endpoint and no new credential: it reads the
 * existing public contract server-side through the same proxy pattern as the
 * home page.
 */
export default async function CoveragePage() {
  const apiUrl = process.env.API_URL?.trim() || null;
  const state = await getCoverage(apiUrl);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-12 lg:px-0">
      <p className="font-mono text-xs uppercase tracking-wider text-ink/70">
        Coverage · what is actually indexed
      </p>
      <h1 className="mt-3 font-sans text-4xl font-bold uppercase leading-tight tracking-tight sm:text-5xl">
        What is actually indexed.
      </h1>
      <p className="mt-5 max-w-2xl font-sans text-lg leading-relaxed text-ink/90">
        The corpus is a nationwide discovery directory with a small set of
        hand-verified central records — not an exhaustive scheme database. This
        page reports the live catalogue split so the difference is visible
        rather than claimed.
      </p>

      {state.kind === "unconfigured" ? (
        <section
          data-testid="coverage-unconfigured"
          className="mt-8 border-2 border-ink bg-paper-dim p-5"
        >
          <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-ink">
            Coverage report unavailable · no API configured
          </h2>
          <p className="mt-2 max-w-2xl font-sans text-sm leading-relaxed text-ink/85">
            This build has no answering API deployed (<code>API_URL</code> is not
            set), so there is no live catalogue to read. The committed corpus
            figures are {CORPUS.documents} documents · {CORPUS.vectors} vectors ·{" "}
            {CORPUS.jurisdictions} jurisdictions, and the method behind them is in
            the evidence page. Nothing here is estimated or filled in.
          </p>
          <p className="mt-3 font-mono text-[11px] text-ink/60">
            <a
              href="/evidence"
              className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
            >
              See the measured evidence →
            </a>
          </p>
        </section>
      ) : null}

      {state.kind === "unavailable" ? (
        <section
          data-testid="coverage-unavailable"
          role="alert"
          className="mt-8 border-2 border-signal bg-paper p-5"
        >
          <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-signal">
            Coverage report unavailable · API not answering
          </h2>
          <p className="mt-2 max-w-2xl font-sans text-sm leading-relaxed text-ink/85">
            The live catalogue could not be read because {state.reason}. The
            committed corpus figures are {CORPUS.documents} documents ·{" "}
            {CORPUS.vectors} vectors · {CORPUS.jurisdictions} jurisdictions; the
            per-jurisdiction report is served by <code>GET /coverage</code> when
            the API is up.
          </p>
          <p className="mt-3 font-mono text-[11px] text-ink/60">
            <a
              href="/coverage"
              className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
            >
              Retry ↻
            </a>{" "}
            ·{" "}
            <a
              href="/evidence"
              className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
            >
              measured evidence →
            </a>
          </p>
        </section>
      ) : null}

      {state.kind === "report" ? (
        <section data-testid="coverage-report" className="mt-8">
          <dl className="grid grid-cols-1 gap-px border border-ink/20 bg-ink/20 sm:grid-cols-3">
            <div className="bg-paper p-4" data-testid="coverage-jurisdictions">
              <dt className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60">
                Jurisdictions
              </dt>
              <dd className="mt-1 font-mono text-2xl font-bold text-ink">
                {state.report.jurisdiction_count ?? "—"}
              </dd>
              <dd className="mt-1 font-sans text-xs text-ink/70">
                {state.report.state_count ?? "—"} states ·{" "}
                {state.report.union_territory_count ?? "—"} union territories
              </dd>
            </div>
            <div className="bg-paper p-4" data-testid="coverage-verified">
              <dt className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60">
                Verified sample records
              </dt>
              <dd className="mt-1 font-mono text-2xl font-bold text-verified">
                {state.report.catalog_sample_verified_count ?? "—"}
              </dd>
              <dd className="mt-1 font-sans text-xs text-ink/70">
                hand-checked against the official source
              </dd>
            </div>
            <div className="bg-paper p-4" data-testid="coverage-total">
              <dt className="font-mono text-[10px] font-bold uppercase tracking-wider text-ink/60">
                Catalogue records
              </dt>
              <dd className="mt-1 font-mono text-2xl font-bold text-ink">
                {state.report.catalog_records_total ?? "—"}
              </dd>
              <dd className="mt-1 font-sans text-xs text-ink/70">
                every record carries a data_status
              </dd>
            </div>
          </dl>

          {state.report.catalog_by_status ? (
            <StatusBreakdown byStatus={state.report.catalog_by_status} />
          ) : null}

          {state.report.coverage_note ? (
            <blockquote
              data-testid="coverage-note"
              className="mt-6 border-l-4 border-ink bg-paper-dim p-4 font-sans text-sm leading-relaxed text-ink/85"
            >
              {state.report.coverage_note}
            </blockquote>
          ) : null}

          {state.report.per_jurisdiction &&
          state.report.per_jurisdiction.length > 0 ? (
            <div className="mt-8">
              <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-ink/70">
                Per-jurisdiction records [{state.report.per_jurisdiction.length}]
              </h2>
              <ul
                data-testid="coverage-jurisdiction-list"
                className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2"
              >
                {state.report.per_jurisdiction.map((entry) => (
                  <li
                    key={`${entry.code ?? entry.name}`}
                    className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/10 py-1.5"
                  >
                    <span className="font-sans text-sm text-ink/90">
                      {entry.name ?? "unnamed"}
                    </span>
                    <span className="font-mono text-[10px] uppercase text-ink/55">
                      {entry.data_status ?? "unknown"} ·{" "}
                      {entry.catalog_record_count ?? 0} rec
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      <p className="mt-8 font-mono text-[11px] leading-relaxed text-ink/60">
        <a
          href="/"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          ← ask a question
        </a>{" "}
        ·{" "}
        <a
          href="/evidence"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          how these numbers were measured →
        </a>
      </p>
    </div>
  );
}
