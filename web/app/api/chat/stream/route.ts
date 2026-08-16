export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/query/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "The SchemeGPT API is unreachable." }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
  if (!upstream.ok || !upstream.body) {
    return new Response(
      JSON.stringify({ error: "The SchemeGPT API rejected the request." }),
      { status: upstream.status ?? 502, headers: { "content-type": "application/json" } },
    );
  }
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
    },
  });
}
