import { Chat } from "../components/Chat";
import { CoveragePill } from "../components/CoveragePill";
import { StaggeredText } from "../components/StaggeredText";

export const dynamic = "force-dynamic";

async function getCoverage(): Promise<{
  jurisdictions: number | null;
  verified: number | null;
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
    const data = await res.json();
    return {
      // Real /coverage keys from app.catalog.coverage_summary():
      // jurisdiction_count and catalog_sample_verified_count.
      jurisdictions: data.jurisdiction_count ?? null,
      verified: data.catalog_sample_verified_count ?? null,
    };
  } catch {
    return { jurisdictions: null, verified: null };
  }
}

export default async function Home() {
  const { jurisdictions, verified } = await getCoverage();
  return (
    <div>
      <section className="px-4 pb-14 pt-16 lg:px-14 lg:pt-24">
        <p className="mb-6 font-mono text-xs uppercase">
          Design &amp; honesty — for every citizen
        </p>
        <h1 className="max-w-5xl font-sans text-[13vw] font-bold uppercase leading-[1.0] tracking-tight sm:text-7xl lg:text-8xl">
          <StaggeredText text="Ask your government." />
        </h1>
        <p className="mt-8 max-w-2xl font-sans text-xl leading-relaxed lg:text-2xl">
          Plain-language answers about Indian government schemes — in broken
          English, Hindi, or anything in between — quoting the exact policy
          statements they rely on.
        </p>
        <div className="mt-6">
          <CoveragePill jurisdictions={jurisdictions} verified={verified} />
        </div>
      </section>
      <Chat />
    </div>
  );
}
