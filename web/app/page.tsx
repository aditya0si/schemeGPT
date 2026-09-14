import { Chat } from "../components/Chat";
import { CoveragePill } from "../components/CoveragePill";
import { StaggeredText } from "../components/StaggeredText";

export const dynamic = "force-dynamic";

async function getCoverage(): Promise<{
  jurisdictions: number | null;
  verified: number | null;
  apiReachable: boolean;
}> {
  const api = process.env.API_URL ?? "http://localhost:8000";
  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`${api}/coverage`, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(t);
    if (!res.ok) {
      return { jurisdictions: null, verified: null, apiReachable: false };
    }
    const data = await res.json();
    return {
      // Real /coverage keys from app.catalog.coverage_summary():
      // jurisdiction_count and catalog_sample_verified_count.
      jurisdictions: data.jurisdiction_count ?? null,
      verified: data.catalog_sample_verified_count ?? null,
      apiReachable: true,
    };
  } catch {
    return { jurisdictions: null, verified: null, apiReachable: false };
  }
}

export default async function Home() {
  const { jurisdictions, verified, apiReachable } = await getCoverage();
  return (
    <div>
      <section className="px-4 pb-10 pt-14 lg:px-14 lg:pt-20">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <p className="font-mono text-xs uppercase tracking-wider text-ink/70">
            Design &amp; honesty — for every citizen
          </p>
          <CoveragePill
            jurisdictions={jurisdictions}
            verified={verified}
            apiReachable={apiReachable}
          />
        </div>

        <h1 className="max-w-5xl font-sans text-[13vw] font-bold uppercase leading-[1.0] tracking-tight sm:text-7xl lg:text-8xl">
          <StaggeredText text="Ask your government." />
        </h1>

        <p className="mt-8 max-w-2xl font-sans text-xl leading-relaxed lg:text-2xl text-ink/90">
          Plain-language answers about Indian government schemes — in broken
          English, Hindi, or anything in between — quoting the exact policy
          statements they rely on.
        </p>

        {!apiReachable ? (
          <div className="mt-6 max-w-2xl border-l-4 border-ink/40 bg-paper-dim p-4">
            <p className="font-mono text-xs font-bold uppercase tracking-wide text-ink">
              API Service Notice
            </p>
            <p className="mt-1 font-sans text-sm leading-relaxed text-ink/80">
              The SchemeGPT backend is currently offline or in cold start (Render free tier sleeps when inactive). Example queries and demo answers remain fully functional.
            </p>
          </div>
        ) : null}
      </section>

      <Chat initialApiReachable={apiReachable} />
    </div>
  );
}
