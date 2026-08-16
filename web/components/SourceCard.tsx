export type Source = {
  source: string;
  content: string;
  jurisdiction?: string | null;
  state?: string | null;
  data_status?: string | null;
  last_verified?: string | null;
  source_url?: string | null;
};

function stampFor(dataStatus: string | null | undefined): {
  label: string;
  className: string;
} {
  if (dataStatus === "sample_verified")
    return { label: "Verified", className: "text-verified" };
  if (dataStatus === "directory_seed")
    return { label: "Directory seed", className: "text-seed" };
  return { label: "Source", className: "text-ink/60" };
}

export function SourceCard({ source }: { source: Source }) {
  const stamp = stampFor(source.data_status);
  const name = source.source.split("/").pop() ?? source.source;
  return (
    <li className="border-t border-ink/25 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] uppercase">{name}</span>
        <span className={`font-mono text-[11px] uppercase ${stamp.className}`}>
          {stamp.label}
          {source.last_verified ? ` · ${source.last_verified}` : ""}
        </span>
      </div>
      {source.source_url ? (
        <a
          href={source.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[11px] text-linkblue underline"
        >
          official source ↗
        </a>
      ) : null}
    </li>
  );
}
