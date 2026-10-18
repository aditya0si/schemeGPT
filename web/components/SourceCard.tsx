export type Source = {
  source: string;
  content: string;
  jurisdiction?: string | null;
  state?: string | null;
  data_status?: string | null;
  last_verified?: string | null;
  source_url?: string | null;
};

/**
 * The status → label contract.
 *
 * Every `data_status` the API can emit (`app/ingest.py`, `app/catalog.py`,
 * `app/retrieval.py`) has an explicit, distinct reader-facing label here. A
 * status this build does not recognise is a defect, not a reason to fall back to
 * a neutral "Source": it renders its raw value so nothing is implied.
 * `tests/test_web_source_labels.py` fails if a status in the backend has no
 * label, if two statuses share one label, or if the neutral fallback returns.
 */
export const STATUS_STAMPS: Record<
  string,
  { label: string; className: string; note: string | null }
> = {
  sample_verified: {
    label: "Verified",
    className: "text-verified font-bold",
    note: null,
  },
  directory_seed: {
    label: "Directory seed",
    className: "text-seed font-bold",
    note:
      "Discovery/coverage entry: it maps the jurisdiction and points at the " +
      "official portal. Its eligibility detail was not individually verified.",
  },
  myscheme_import: {
    label: "Imported · unverified",
    className: "text-seed font-bold",
    note:
      "Automated import from the national MyScheme portal, quoted as stored. " +
      "No human has reviewed this record, so it is not a verified source.",
  },
  unknown: {
    label: "Provenance unlabelled",
    className: "text-ink/60",
    note:
      "The stored record carries no data_status. Nothing about its provenance " +
      "is known, and none is implied.",
  },
};

const UNRECOGNISED_CLASS = "text-signal font-bold";

function stampFor(dataStatus: string | null | undefined): {
  label: string;
  className: string;
  note: string | null;
  key: string;
} {
  const key = (dataStatus ?? "unknown").trim().toLowerCase();
  const known = STATUS_STAMPS[key];
  if (known) return { ...known, key };
  return {
    label: `Unrecognised status · ${dataStatus}`,
    className: UNRECOGNISED_CLASS,
    note:
      "This build has no reader-facing label for this provenance value, so it " +
      "is shown raw rather than guessed.",
    key: "unrecognised",
  };
}

export function SourceCard({ source }: { source: Source }) {
  const stamp = stampFor(source.data_status);
  const name = source.source.split("/").pop() ?? source.source;
  return (
    <li className="py-2.5" data-testid="source-card" data-status={stamp.key}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] font-bold uppercase text-ink">{name}</span>
        <span className={`font-mono text-[11px] uppercase ${stamp.className}`}>
          {stamp.label}
          {source.last_verified ? ` · ${source.last_verified}` : ""}
        </span>
      </div>
      {stamp.note ? (
        <p className="mt-1 max-w-xl font-mono text-[10px] leading-relaxed text-ink/60">
          {stamp.note}
        </p>
      ) : null}
      {source.last_verified ? null : (
        <p
          data-testid="source-verified-date-absent"
          className="mt-0.5 font-mono text-[10px] uppercase text-ink/45"
        >
          no verification date on record
        </p>
      )}
      {source.source_url ? (
        <a
          href={source.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 inline-block font-mono text-[11px] text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          official source ↗
        </a>
      ) : (
        <p
          data-testid="source-url-absent"
          className="mt-0.5 font-mono text-[10px] uppercase text-ink/45"
        >
          no per-document source URL stored — portal record, not a citation
        </p>
      )}
    </li>
  );
}
