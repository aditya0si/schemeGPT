import { MetricsPanel } from "../../components/MetricsPanel";
import { EVIDENCE } from "../../lib/measured";

/**
 * /evidence — the measured record, reachable in one click from the homepage.
 *
 * Deliberately independent of the live API: the numbers are frozen, committed
 * measurements, so this page renders identically whether the deployment has an
 * API base URL configured, is cold-starting, or has no backend at all. `tests/test_web_routes.py` fails if this
 * page ever becomes conditional on the API, and `tests/test_web_measured_guard.py`
 * re-derives every figure from the document that records it.
 */
export const metadata = {
  title: "Evidence — SchemeGPT",
  description:
    "Frozen, committed measurements behind SchemeGPT: retrieval gate, temporal as-of gate, PII benchmark and corpus coverage.",
};

export default function EvidencePage() {
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-12 lg:px-0">
      <p className="font-mono text-xs uppercase tracking-wider text-ink/70">
        Evidence · frozen measurements
      </p>
      <h1 className="mt-3 font-sans text-4xl font-bold uppercase leading-tight tracking-tight sm:text-5xl">
        The numbers, and where they come from.
      </h1>
      <p className="mt-5 max-w-2xl font-sans text-lg leading-relaxed text-ink/90">
        Each figure below is a measurement from a real run, copied into the UI
        from the committed document that records it. Nothing here is an estimate,
        a target, or a rounded-up summary — and nothing here depends on a live
        API being up.
      </p>

      <section className="mt-8" aria-label="Measured results">
        <MetricsPanel />
      </section>

      <section className="mt-10 border border-ink/20 bg-paper-dim/40 p-5">
        <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-ink/70">
          How to reproduce
        </h2>
        <p className="mt-2 font-sans text-sm leading-relaxed text-ink/85">
          Every card links to the evidence document that records its exact
          command, corpus generation and date. The short version, from the repo
          root:
        </p>
        <pre className="mt-3 overflow-x-auto border-l-4 border-ink bg-paper p-3 font-mono text-[11px] leading-relaxed text-ink/90">
{`python -m eval.retrieval_gate                  # retrieval gate (needs DB + ingested corpus)
./.venv/Scripts/python.exe -m eval.temporal_gate --check-default-mode
GROQ_API_KEY="" python -m eval.pii_benchmark
python -m pytest -q tests/test_web_measured_guard.py   # this page vs the documents`}
        </pre>
        <p className="mt-3 font-sans text-xs leading-relaxed text-ink/70">
          The retrieval gate is published for two runtimes — an fp32 PyTorch
          local run and the hosted image&apos;s int8 ONNX encoder — and both
          values are labelled with the runtime that produced them. The gate
          floors (Hit@4 ≥ 0.85, MRR@4 ≥ 0.60) are the same for both and were
          never lowered.
        </p>
      </section>

      <section className="mt-8 border-l-4 border-signal bg-paper-dim p-5">
        <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-signal">
          What this page is not
        </h2>
        <ul className="mt-2 space-y-1.5 font-sans text-sm leading-relaxed text-ink/85">
          <li>
            Not a live benchmark: these are frozen runs on one corpus
            generation, not a production SLO.
          </li>
          <li>
            Not a generation-quality claim: the retrieval gate measures
            retrieval only, with no LLM judge involved.
          </li>
          <li>
            Not an independent audit: the evidence is reproducible by anyone,
            but it was produced by the same repository it describes.
          </li>
        </ul>
      </section>

      <p className="mt-8 font-mono text-[11px] leading-relaxed text-ink/60">
        <a
          href="/"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          ← ask a question
        </a>{" "}
        ·{" "}
        <a
          href="/coverage"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          see what the corpus covers →
        </a>{" "}
        ·{" "}
        <a
          href={EVIDENCE.repository}
          target="_blank"
          rel="noopener noreferrer"
          className="text-linkblue underline hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
        >
          repository ↗
        </a>
      </p>
    </div>
  );
}
