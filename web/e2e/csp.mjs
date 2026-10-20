// Response-header / CSP probe over a *real Next production build*.
//
// Finding F1 shipped a static header set from web/next.config.ts. Source-level
// regression tests can only prove the policy is still written down; this script
// proves the running app actually emits it, that a browser accepts the policy,
// and that nothing in the rendered app is blocked by it.
//
//   node web/e2e/stub-api.mjs --port 8099            # terminal 1
//   npm --prefix web run build                       # once
//   API_URL=http://127.0.0.1:8099 npx --prefix web next start -p 3100   # terminal 2
//   node web/e2e/csp.mjs --base http://127.0.0.1:3100
//
// What it proves:
//   1. every route shape carries the identical policy: a prerendered page
//      (/evidence), dynamic pages (/, /coverage) and both route handlers;
//   2. X-Content-Type-Options, Referrer-Policy, the clickjacking pair
//      (frame-ancestors + X-Frame-Options) and Permissions-Policy are present,
//      and X-Powered-By is gone;
//   3. with the policy enforced, the browser reports zero securitypolicyviolation
//      events on /, /evidence and /coverage, and no resource is blocked;
//   4. the app still works under the policy: it hydrates, streams an answer,
//      records feedback through /api/chat/feedback, styles and the self-hosted
//      next/font faces load, and a same-origin iframe of /evidence is refused.
//
// Exit code 0 = every check passed. Non-zero = at least one check failed; the
// failing line names the check and the observed detail.

import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
};
const BASE = arg("base", "http://127.0.0.1:3100").replace(/\/$/, "");

// Resolve a browser binary: CHROME_PATH wins, then the standard Windows install
// locations, then the headless Chromium this environment provisions. Exiting
// loudly is deliberate — a probe that silently skipped its browser layer would
// leave the CSP claim unproven while still reporting success.
const CHROME = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  process.env.LOCALAPPDATA
    ? path.join(
        process.env.LOCALAPPDATA,
        "hermes",
        "tools",
        "chromium-1208",
        "chrome-win64",
        "chrome.exe",
      )
    : undefined,
]
  .filter(Boolean)
  .find((candidate) => existsSync(candidate));

if (!CHROME) {
  console.error(
    "No Chrome/Edge binary found. Point CHROME_PATH at one, e.g.\n" +
      "  CHROME_PATH='C:/Program Files/Google/Chrome/Application/chrome.exe' node web/e2e/csp.mjs",
  );
  process.exit(2);
}

const results = [];
const consoleErrors = [];
const expectedErrors = [];
const failedRequests = [];
// The clickjacking probe deliberately frames /evidence and must be refused.
// Browsers surface that refusal as an ERR_BLOCKED_BY_RESPONSE document load and
// a frame-ancestors console message; those two are collected here as *evidence*
// of enforcement instead of being counted as defects, and the check below
// requires them to appear.
const frameBlocks = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

// --- 1. HTTP layer: what the server actually sends ---------------------------
// The expected policy is asserted literally rather than re-derived from
// next.config.ts, so a silent edit to the config cannot make this probe agree
// with itself. Keep it in step with tests/test_web_security_headers.py.
const EXPECTED_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
].join("; ");

const ROUTES = [
  { name: "GET / (dynamic page)", path: "/", method: "GET" },
  { name: "GET /evidence (prerendered page)", path: "/evidence", method: "GET" },
  { name: "GET /coverage (dynamic page)", path: "/coverage", method: "GET" },
  {
    name: "POST /api/chat/stream (route handler, SSE)",
    path: "/api/chat/stream",
    method: "POST",
    body: { question: "How much does PM-KISAN provide?" },
  },
  {
    name: "POST /api/chat/feedback (route handler, JSON)",
    path: "/api/chat/feedback",
    method: "POST",
    body: { question: "q", answer: "a", rating: "up", language: "en" },
  },
];

function parseCsp(value) {
  const out = new Map();
  for (const part of value.split(";")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const [directive, ...sources] = trimmed.split(/\s+/);
    out.set(directive, sources.join(" "));
  }
  return out;
}

const observed = [];
for (const route of ROUTES) {
  const response = await fetch(`${BASE}${route.path}`, {
    method: route.method,
    headers: route.body ? { "content-type": "application/json" } : undefined,
    body: route.body ? JSON.stringify(route.body) : undefined,
    redirect: "manual",
  });
  const headers = response.headers;
  const csp = headers.get("content-security-policy");
  observed.push({
    route,
    status: response.status,
    contentType: headers.get("content-type"),
    csp,
    xcto: headers.get("x-content-type-options"),
    xfo: headers.get("x-frame-options"),
    referrer: headers.get("referrer-policy"),
    permissions: headers.get("permissions-policy"),
    coop: headers.get("cross-origin-opener-policy"),
    poweredBy: headers.get("x-powered-by"),
  });
  // Drain the body so the connection is reusable.
  try {
    await response.arrayBuffer();
  } catch {
    /* streaming responses may not buffer; the header assertions already ran */
  }
}

console.log("\nobserved response headers");
for (const row of observed) {
  console.log(`  ${row.route.name} -> ${row.status} (${row.contentType ?? "no content-type"})`);
  console.log(`    content-security-policy: ${row.csp ?? "MISSING"}`);
  console.log(
    `    x-content-type-options: ${row.xcto ?? "MISSING"} | x-frame-options: ${row.xfo ?? "MISSING"}` +
      ` | referrer-policy: ${row.referrer ?? "MISSING"}`,
  );
  console.log(`    permissions-policy: ${row.permissions ?? "MISSING"}`);
  console.log(`    x-powered-by: ${row.poweredBy ?? "absent"}`);
}
console.log("");

const missing = observed.filter((row) => !row.csp).map((row) => row.route.name);
check(
  "every route shape carries a Content-Security-Policy",
  missing.length === 0,
  missing.length ? `missing on ${missing.join(", ")}` : `${observed.length}/${observed.length} routes`,
);

const distinct = [...new Set(observed.map((row) => row.csp).filter(Boolean))];
check(
  "the policy is identical on static, dynamic and route-handler responses",
  distinct.length === 1,
  distinct.length === 1 ? "1 distinct value" : `${distinct.length} distinct values`,
);

const policy = distinct.length === 1 ? distinct[0] : "";
const directives = parseCsp(policy);
check(
  "the policy is exactly the reviewed directive set",
  policy === EXPECTED_CSP,
  policy === EXPECTED_CSP ? "byte-identical" : `observed: ${policy}`,
);
check(
  "the prerendered /evidence page is covered, not only dynamic routes",
  Boolean(observed[1].csp) && observed[1].csp === policy,
);
check(
  "frame-ancestors 'none' and X-Frame-Options: DENY are both present (clickjacking)",
  directives.get("frame-ancestors") === "'none'" &&
    observed.every((row) => (row.xfo ?? "").toLowerCase() === "deny"),
);
check(
  "X-Content-Type-Options: nosniff on every route shape",
  observed.every((row) => (row.xcto ?? "").toLowerCase() === "nosniff"),
);
check(
  "Referrer-Policy: strict-origin-when-cross-origin on every route shape",
  observed.every((row) => (row.referrer ?? "").toLowerCase() === "strict-origin-when-cross-origin"),
);
check(
  "Permissions-Policy denies camera/microphone/geolocation/payment/usb",
  observed.every(
    (row) =>
      row.permissions === "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  ),
  observed[0].permissions ?? "MISSING",
);
check(
  "X-Powered-By is not sent",
  observed.every((row) => !row.poweredBy),
  observed.find((row) => row.poweredBy)?.poweredBy ?? "absent everywhere",
);
check(
  "the SSE route handler still streams (text/event-stream)",
  (observed[3].contentType ?? "").includes("text/event-stream") && observed[3].status === 200,
  `${observed[3].status} ${observed[3].contentType}`,
);
check(
  "the feedback route handler still answers JSON",
  (observed[4].contentType ?? "").includes("application/json") && observed[4].status === 200,
  `${observed[4].status} ${observed[4].contentType}`,
);

// --- 2. Browser layer: the policy as the browser enforces it ----------------
// The violation listener is installed before the first navigation, so it also
// catches violations during initial parse/hydration, not just after load.
const CSP_HOOK = `
  window.__cspViolations = [];
  document.addEventListener('securitypolicyviolation', (event) => {
    window.__cspViolations.push({
      directive: event.effectiveDirective || event.violatedDirective,
      blockedURI: event.blockedURI,
      sample: event.sample,
      disposition: event.disposition,
    });
  }, true);
`;

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${path.join(process.env.TEMP ?? ".", `csp-${Date.now()}`)}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--hide-scrollbars",
    "about:blank",
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);

const wsUrl = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("chrome did not report a devtools endpoint")), 20000);
  chrome.stderr.on("data", (buf) => {
    const match = /ws:\/\/[^\s]+/.exec(String(buf));
    if (match) {
      clearTimeout(timer);
      resolve(match[0]);
    }
  });
});

const ws = new WebSocket(wsUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", reject, { once: true });
});

let nextId = 0;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id !== undefined && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    return;
  }
  if (msg.method === "Runtime.exceptionThrown") {
    consoleErrors.push(`exception: ${msg.params.exceptionDetails?.text ?? "unknown"}`);
  }
  if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
    consoleErrors.push(
      `console.error: ${(msg.params.args ?? []).map((a) => a.value ?? a.description ?? "?").join(" ")}`,
    );
  }
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    const { text, url = "" } = msg.params.entry;
    // The site has no favicon yet — a known, documented gap unrelated to CSP.
    if (url.includes("/favicon") || text.includes("/favicon")) {
      expectedErrors.push(`${url} favicon 404 (known gap)`);
    } else if (/frame-ancestors/i.test(text)) {
      // Only the deliberate framing probe can produce this.
      frameBlocks.push(`console: ${text}`);
    } else if (/content security policy|csp/i.test(text)) {
      consoleErrors.push(`CSP: ${text}${url ? ` (${url})` : ""}`);
    } else {
      consoleErrors.push(`log: ${text}${url ? ` (${url})` : ""}`);
    }
  }
  if (msg.method === "Network.loadingFailed" && !msg.params.canceled) {
    if (/ERR_BLOCKED_BY_RESPONSE/.test(msg.params.errorText)) {
      // Response-level refusal (frame-ancestors / X-Frame-Options) — the only
      // framed document in this probe is the deliberate one.
      frameBlocks.push(`network: ${msg.params.type} ${msg.params.errorText}`);
    } else {
      failedRequests.push(`${msg.params.type} ${msg.params.errorText}`);
    }
  }
});

const send = (sessionId, method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });

const { targetId } = await send(undefined, "Target.createTarget", { url: "about:blank" });
const { sessionId } = await send(undefined, "Target.attachToTarget", { targetId, flatten: true });
for (const domain of ["Page", "Runtime", "Log", "Network"]) {
  await send(sessionId, `${domain}.enable`, domain === "Network" ? { maxTotalBufferSize: 1e6 } : {});
}
await send(sessionId, "Page.addScriptToEvaluateOnNewDocument", { source: CSP_HOOK });

const evaluate = async (expression) => {
  const { result, exceptionDetails } = await send(sessionId, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.text ?? "evaluate failed");
  return result.value;
};

async function waitFor(expression, { timeout = 20000, label = expression } = {}) {
  const started = Date.now();
  for (;;) {
    if (await evaluate(expression)) return true;
    if (Date.now() - started > timeout) throw new Error(`timed out waiting for ${label}`);
    await new Promise((r) => setTimeout(r, 150));
  }
}

async function goto(url) {
  await send(sessionId, "Page.navigate", { url });
  await waitFor("document.readyState === 'complete'", { label: `load ${url}` });
}

const violations = async () => evaluate("window.__cspViolations || []");

try {
  // 2.1 — the homepage: no violations, and it hydrates ---------------------
  await send(sessionId, "Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await goto(`${BASE}/`);
  await waitFor("typeof window.__next_f !== 'undefined'", { label: "RSC flight payload" });
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((b) => /PM-KISAN/.test(b.innerText));
    if (!button) throw new Error('sample-query button not found — the page did not hydrate');
    button.click();
  })()`);
  await waitFor("!!document.querySelector('[data-testid=\"source-card\"]')", {
    label: "streamed answer rendered (connect-src 'self' allowed the fetch)",
  });
  const home = await evaluate(`(() => ({
    violations: window.__cspViolations,
    body: document.body.innerText.toLowerCase(),
    fonts: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family),
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyFont: getComputedStyle(document.body).fontFamily,
    resources: performance.getEntriesByType('resource').length,
  }))()`);
  check("/ reports zero securitypolicyviolation events", home.violations.length === 0, JSON.stringify(home.violations));
  check(
    "the answer streamed under connect-src 'self'",
    home.body.includes("pm-kisan") && home.body.includes("verified source quotes"),
  );
  check(
    "stylesheets applied under style-src (paper background, expected type)",
    home.bodyBg === "rgb(251, 250, 244)",
    home.bodyBg,
  );
  check(
    "self-hosted next/font faces loaded under font-src 'self'",
    home.fonts.length > 0 && /archivo/i.test(home.bodyFont),
    `${home.fonts.length} face(s): ${home.bodyFont}`,
  );
  check("subresources loaded under the policy", home.resources > 0, `${home.resources} resources`);

  // 2.2 — feedback through the real UI control ------------------------------
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((b) => /helpful/i.test(b.innerText) && !/not/i.test(b.innerText));
    if (!button) throw new Error('feedback control not found');
    button.click();
  })()`);
  const direct = await evaluate(`fetch('/api/chat/feedback', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ question: 'csp probe', answer: 'probe', rating: 'up', language: 'en' }),
  }).then((r) => ({ ok: r.ok, status: r.status })).catch((e) => ({ ok: false, status: String(e) }))`);
  await waitFor("document.body.innerText.toLowerCase().includes('feedback recorded')", {
    label: "feedback confirmation",
  });
  check(
    "feedback POST is permitted by connect-src 'self' (UI control + direct fetch)",
    direct.ok && direct.status === 200,
    `fetch -> ${direct.status}`,
  );

  // 2.3 — the prerendered /evidence route ----------------------------------
  await goto(`${BASE}/evidence`);
  const evidence = await evaluate(`(() => ({
    violations: window.__cspViolations,
    metrics: document.querySelectorAll('[data-testid^="metric-"]').length,
    text: document.body.innerText.toLowerCase(),
  }))()`);
  check("/evidence reports zero securitypolicyviolation events", evidence.violations.length === 0, JSON.stringify(evidence.violations));
  check("/evidence renders its measured cards under the policy", evidence.metrics === 4, `${evidence.metrics} cards`);
  check("/evidence still publishes both MRR@4 runtimes", evidence.text.includes("0.802083") && evidence.text.includes("0.796875"));

  // 2.4 — the dynamic /coverage route --------------------------------------
  await goto(`${BASE}/coverage`);
  await waitFor("!!document.querySelector('[data-testid=\"coverage-report\"]')", { label: "coverage report" });
  const coverage = await evaluate(`(() => ({
    violations: window.__cspViolations,
    rows: document.querySelectorAll('[data-testid="coverage-jurisdiction-list"] li').length,
  }))()`);
  check("/coverage reports zero securitypolicyviolation events", coverage.violations.length === 0, JSON.stringify(coverage.violations));
  check("/coverage renders its report under the policy", coverage.rows > 0, `${coverage.rows} rows`);

  // 2.5 — Permissions-Policy is compatible: denied, not broken -------------
  await goto(`${BASE}/`);
  const permissions = await evaluate(`(async () => {
    const probe = async (name) => {
      try { return (await navigator.permissions.query({ name })).state; } catch (e) { return 'unsupported'; }
    };
    return { geolocation: await probe('geolocation'), camera: await probe('camera'), microphone: await probe('microphone') };
  })()`);
  check(
    "Permissions-Policy denies geolocation/camera/microphone without breaking the page",
    permissions.geolocation === "denied" && permissions.camera === "denied" && permissions.microphone === "denied",
    JSON.stringify(permissions),
  );

  // 2.6 — frame-ancestors refuses a same-origin iframe ---------------------
  const framed = await evaluate(`new Promise((resolve) => {
    const frame = document.createElement('iframe');
    frame.src = '/evidence';
    frame.style.cssText = 'width:400px;height:300px';
    document.body.appendChild(frame);
    setTimeout(() => {
      let text = '';
      let docUrl = '';
      try { text = frame.contentDocument ? frame.contentDocument.body.innerText : ''; docUrl = frame.contentDocument ? frame.contentDocument.URL : ''; }
      catch (e) { text = 'inaccessible'; docUrl = 'inaccessible'; }
      frame.remove();
      resolve({ text: text.slice(0, 120), docUrl });
    }, 2500);
  })`);
  check(
    "a same-origin iframe of /evidence is refused by frame-ancestors 'none'",
    !/mrr@4|measured/i.test(framed.text),
    `docUrl=${framed.docUrl || "about:blank"} text=${JSON.stringify(framed.text.slice(0, 40))}`,
  );

  // 2.7 — nothing was blocked except the deliberate frame, nothing threw -----
  const blocked = failedRequests.filter((entry) => /ERR_BLOCKED_BY_CSP|csp/i.test(entry));
  check("no subresource was blocked by CSP", blocked.length === 0, blocked.join(" | "));
  check(
    "frame-ancestors enforcement is observable (blocked document load + console refusal)",
    frameBlocks.some((entry) => entry.startsWith("network:")) &&
      frameBlocks.some((entry) => entry.startsWith("console:")),
    frameBlocks.length ? frameBlocks.join(" | ") : "no refusal observed — the policy did not take effect",
  );
  check("no failed requests in the probed paths", failedRequests.length === 0, failedRequests.join(" | "));
  check("no client-side JS errors in the probed paths", consoleErrors.length === 0, consoleErrors.join(" | "));
} catch (error) {
  check("probe completed without an unhandled error", false, String(error));
} finally {
  ws.close();
  chrome.kill();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
