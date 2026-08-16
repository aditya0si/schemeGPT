export function CoveragePill({
  jurisdictions,
  verified,
}: {
  jurisdictions: number | null;
  verified: number | null;
}) {
  if (jurisdictions == null) return null;
  return (
    <p className="font-mono text-xs uppercase text-ink/70">
      {jurisdictions} jurisdictions
      {verified != null ? ` · ${verified} verified sample schemes` : ""} ·
      state directories expanding
    </p>
  );
}
