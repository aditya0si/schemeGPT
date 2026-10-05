export function CoveragePill({
  jurisdictions,
  verified,
  apiReachable = true,
}: {
  jurisdictions: number | null;
  verified: number | null;
  apiReachable?: boolean;
}) {
  if (!apiReachable || jurisdictions == null) {
    return (
      <div className="inline-flex items-center gap-2 border border-ink/25 bg-paper-dim px-3 py-1 font-mono text-[11px] uppercase tracking-wide text-ink/70">
        <span className="h-2 w-2 bg-seed" aria-hidden="true" />
        <span>API Standby · Demo Fallback Active</span>
      </div>
    );
  }
  return (
    <div className="inline-flex items-center gap-2 border border-ink/25 bg-paper px-3 py-1 font-mono text-[11px] uppercase tracking-wide text-ink/75">
      <span className="h-2 w-2 bg-verified" aria-hidden="true" />
      <span>
        {jurisdictions} jurisdictions
        {verified != null ? ` · ${verified} verified sample schemes` : ""} ·
        state directories expanding
      </span>
    </div>
  );
}
