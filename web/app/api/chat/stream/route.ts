import {
  OFFLINE_ERROR,
  PUBLISHED_MEASUREMENTS,
} from "../../../../lib/measured";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read the API endpoint at request time. `undefined` (or blank) is a definitive
// "not configured" state, distinct from "configured but currently unreachable".
function configuredApiUrl(): string | null {
  const raw = process.env.API_URL;
  if (typeof raw !== "string" || raw.trim() === "") return null;
  return raw.trim();
}

export async function POST(req: Request) {
  const apiUrl = configuredApiUrl();

  if (apiUrl === null) {
    // No backend is configured. This is permanent and honest: return a
    // structured offline record (with the project's real measured numbers)
    // instead of a transient "retry in 30 seconds" promise.
    return new Response(
      JSON.stringify({
        offline: true,
        error: OFFLINE_ERROR,
        measured: PUBLISHED_MEASUREMENTS,
      }),
      {
        status: 501,
        headers: {
          "content-type": "application/json",
          "cache-control": "no-store",
        },
      },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl}/query/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return new Response(
      JSON.stringify({
        error:
          "The SchemeGPT API is unreachable. If the backend is on a free tier, it may be waking up from sleep — please retry in 30 seconds.",
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
  if (!upstream.ok || !upstream.body) {
    return new Response(
      JSON.stringify({
        error:
          "The SchemeGPT API rejected the request. Please verify the question or retry shortly.",
      }),
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
