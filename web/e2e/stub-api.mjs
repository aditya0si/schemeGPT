// Stub SchemeGPT API for the browser journey (web/e2e/journey.mjs).
//
// Deterministic, offline, zero dependencies and zero cost: it answers the SSE
// contract the real API speaks, with the same source provenance the live
// deployment returns (one verified record plus portal imports), plus a failure
// and an edge-case exit so the UI's error and fallback paths can be exercised
// without touching Groq, Postgres or the deployed services.
//
//   node web/e2e/stub-api.mjs [--port 8099]

import http from "node:http";

const port = (() => {
  const i = process.argv.indexOf("--port");
  return i === -1 ? 8099 : Number(process.argv[i + 1]);
})();

const VERIFIED = {
  source: "schemes/pm-kisan.md",
  content:
    "PM-KISAN provides income support of Rs.6000/- per annum to landholding farmer families.",
  jurisdiction: "central",
  state: null,
  data_status: "sample_verified",
  last_verified: "2026-09-20",
  source_url: "https://pmkisan.gov.in/",
};

// What the live deployment actually returns for 3 of its 4 retrieved chunks:
// portal imports with no source_url and no last_verified.
const IMPORT = (slug) => ({
  source: `myscheme/${slug}.md`,
  content: `Imported portal record for ${slug}.`,
  jurisdiction: "central",
  state: null,
  data_status: "myscheme_import",
  last_verified: null,
  source_url: null,
});

// The provenance edge cases: a directory seed, a record with no status at all,
// and a status this build of the UI has never seen.
const EDGE = [
  {
    source: "states/bihar.md",
    content: "Bihar state directory seed.",
    jurisdiction: "bihar",
    state: "Bihar",
    data_status: "directory_seed",
    last_verified: null,
    source_url: "https://myscheme.gov.in/",
  },
  {
    source: "misc/legacy-record.md",
    content: "Record ingested before data_status existed.",
    jurisdiction: null,
    state: null,
    data_status: null,
    last_verified: null,
    source_url: null,
  },
  {
    source: "misc/future-record.md",
    content: "Record carrying a status this build cannot label.",
    jurisdiction: null,
    state: null,
    data_status: "mystery_status",
    last_verified: null,
    source_url: null,
  },
];

const ANSWER =
  "PM-KISAN gives each eligible farmer family Rs 6,000 per year, paid in three instalments.";

function sourcesFor(question) {
  if (/edge/i.test(question)) return EDGE;
  return [VERIFIED, IMPORT("afag"), IMPORT("pm-kusum")];
}

function sse(res, question) {
  const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  res.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache, no-transform",
  });
  send("sources", sourcesFor(question));
  for (const word of ANSWER.split(" ")) send("token", { text: `${word} ` });
  send("quotes", [
    {
      text: "Income support of Rs.6000/- per annum",
      source: VERIFIED.source,
      status: "sample_verified",
      verified: true,
      matched_source: VERIFIED.source,
    },
  ]);
  send("done", { mode: "live", notice: null });
  res.end();
}

const COVERAGE = {
  jurisdiction_count: 36,
  state_count: 28,
  union_territory_count: 8,
  catalog_records_total: 42,
  catalog_sample_verified_count: 6,
  catalog_directory_seed_count: 36,
  catalog_by_status: { directory_seed: 36, sample_verified: 6 },
  per_jurisdiction: [
    { name: "Bihar", code: "BR", type: "state", data_status: "directory_seed", catalog_record_count: 1 },
    { name: "Kerala", code: "KL", type: "state", data_status: "directory_seed", catalog_record_count: 1 },
    { name: "Puducherry", code: "PY", type: "union_territory", data_status: "directory_seed", catalog_record_count: 1 },
  ],
  coverage_note:
    "The corpus is a nationwide state/UT discovery directory, not an exhaustive verified scheme database. (stub payload of the real GET /coverage contract)",
};

const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/coverage") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(COVERAGE));
    return;
  }
  if (req.method === "GET" && req.url === "/readyz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ready", mode: "live" }));
    return;
  }
  if (req.method === "POST" && req.url === "/query/stream") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      let question = "";
      try {
        question = String(JSON.parse(body).question ?? "");
      } catch {
        question = "";
      }
      if (question.trim().length < 2) {
        // The real API's validation path: 422 with a detail the proxy collapses.
        res.writeHead(422, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: "question must be at least 2 characters" }));
        return;
      }
      if (/boom/i.test(question)) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: "stub: deliberate upstream failure" }));
        return;
      }
      sse(res, question);
    });
    return;
  }
  res.writeHead(404, { "content-type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`stub-api listening on http://127.0.0.1:${port}`);
});
