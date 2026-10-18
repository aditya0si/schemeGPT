import { OFFLINE_ERROR } from "../lib/measured";
import { MetricsPanel } from "./MetricsPanel";

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

      <div className="mt-5">
        <MetricsPanel />
      </div>

    </section>
  );
}
