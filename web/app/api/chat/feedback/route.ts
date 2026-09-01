// Server-side proxy for POST /feedback: the browser only ever talks to the
// Next.js app, mirroring the /api/chat/stream proxy.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const upstream = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await req.text(),
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
