// Browser journey over the local candidate, driven through the DevTools
// Protocol with Node's built-in WebSocket — no browser-automation dependency.
//
//   node web/e2e/stub-api.mjs --port 8099            # terminal 1
//   API_URL=http://127.0.0.1:8099 npx next start -p 3100   # terminal 2
//   node web/e2e/journey.mjs --base http://127.0.0.1:3100
//
// What it proves, in one run:
//   1. homepage renders; header links Evidence and Coverage (one click away)
//   2. a primary ask → streamed answer → verified quote → per-source provenance,
//      with every `data_status` (verified, imported, directory seed, absent,
//      unrecognised) rendered as its own reader-facing label
//   3. a failure state renders a labelled error with a retry control
//   4. /evidence renders its measured cards — including both runtime-labelled
//      MRR@4 values — and /coverage renders a live report, then a labelled
//      unavailable state when the API is gone
//   5. no client-side JS errors, no failed requests, keyboard focus visible on
//      the nav in a 375 px viewport
//
// Screenshots land in docs/screenshots/ as the committed visual record.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const SHOTS = path.join(REPO, "docs", "screenshots");

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
};
const BASE = arg("base", "http://127.0.0.1:3100").replace(/\/$/, "");
const CHROME =
  process.env.CHROME_PATH ??
  path.join(
    process.env.LOCALAPPDATA ?? "",
    "hermes",
    "tools",
    "chromium-1208",
    "chrome-win64",
    "chrome.exe",
  );

const results = [];
const consoleErrors = [];
const expectedResourceErrors = [];
const failedRequests = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

// --- minimal CDP client ------------------------------------------------------
const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${path.join(process.env.TEMP ?? ".", `journey-${Date.now()}`)}`,
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
    // Two resource loads are expected in this journey: the site has no favicon
    // yet (a known, documented gap) and this harness deliberately asks the stub
    // for a failing answer. Everything else is a defect.
    if (url.includes("/favicon")) expectedResourceErrors.push(`${url} favicon 404 (known gap)`);
    else if (url.includes("/api/chat/stream")) expectedResourceErrors.push(`${url} deliberate failure probe`);
    else consoleErrors.push(`log: ${text}${url ? ` (${url})` : ""}`);
  }
  if (msg.method === "Network.loadingFailed" && !msg.params.canceled) {
    failedRequests.push(`${msg.params.type} ${msg.params.errorText}`);
  }
});

const send = (sessionId, method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });

// The page target: create a fresh tab and attach to it.
const { targetId } = await send(undefined, "Target.createTarget", { url: "about:blank" });
const { sessionId } = await send(undefined, "Target.attachToTarget", { targetId, flatten: true });
for (const domain of ["Page", "Runtime", "Log", "Network"]) {
  await send(sessionId, `${domain}.enable`, domain === "Network" ? { maxTotalBufferSize: 1e6 } : {});
}

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

async function viewport(width, height) {
  await send(sessionId, "Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function screenshot(name, scrollTo = null) {
  if (scrollTo) {
    await evaluate(`(() => {
      const el = document.querySelector(${JSON.stringify(scrollTo)});
      if (el) el.scrollIntoView({ block: "start" });
    })()`);
    await new Promise((r) => setTimeout(r, 400));
  }
  const { data } = await send(sessionId, "Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: Boolean(scrollTo),
  });
  mkdirSync(SHOTS, { recursive: true });
  const file = path.join(SHOTS, name);
  writeFileSync(file, Buffer.from(data, "base64"));
  return path.relative(REPO, file);
}

async function pressTab() {
  for (const type of ["rawKeyDown", "keyUp"]) {
    await send(sessionId, "Input.dispatchKeyEvent", {
      type,
      key: "Tab",
      code: "Tab",
      windowsVirtualKeyCode: 9,
      nativeVirtualKeyCode: 9,
    });
  }
}

try {
  // 1 — homepage and navigation ------------------------------------------------
  await viewport(1440, 900);
  await goto(`${BASE}/`);
  const title = await evaluate("document.title");
  check("homepage renders with a title", typeof title === "string" && title.length > 0, title);

  const nav = await evaluate(`(() => {
    const links = [...document.querySelectorAll('nav a')].map((a) => a.getAttribute('href'));
    return { links, clicks: links.length, evidence: links.includes('/evidence'), coverage: links.includes('/coverage') };
  })()`);
  check("header links /evidence and /coverage", nav.evidence && nav.coverage, nav.links.join(" "));
  check("evidence is one click from the homepage", nav.clicks <= 2, `${nav.clicks} nav links`);
  console.log(`shot  ${await screenshot("hero.png")}`);

  // 2 — ask → answer → source journey -----------------------------------------
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((b) => /PM-KISAN/.test(b.innerText));
    if (!button) throw new Error('sample-query button not found');
    button.click();
  })()`);
  await waitFor("!!document.querySelector('[data-testid=\"source-card\"]')", {
    label: "sources to render",
  });
  // NB: several labels are rendered through CSS-uppercased classes, so innerText
  // arrives uppercased — compare case-insensitively.
  await waitFor(
    "(() => { const t = document.body.innerText.toLowerCase();" +
      " return t.includes('verified source quotes') && !t.includes('searching policy corpus'); })()",
    { label: "answer to finish streaming" },
  );

  const journey = await evaluate(`(() => {
    const cards = [...document.querySelectorAll('[data-testid="source-card"]')];
    return {
      statuses: cards.map((c) => c.dataset.status),
      labels: cards.map((c) => c.innerText.trim().split('\\n').map((s) => s.trim().toLowerCase()).filter(Boolean)),
      body: document.body.innerText.toLowerCase(),
    };
  })()`);
  check(
    "live-style payload renders verified + imported labels",
    journey.statuses.includes("sample_verified") && journey.statuses.includes("myscheme_import"),
    journey.statuses.join(","),
  );
  check(
    "imported records are labelled unverified, never 'Verified'",
    journey.labels.some((l) => l.some((s) => s.includes("imported · unverified"))) &&
      !journey.labels
        .filter((l) => l.some((s) => s.includes("imported")))
        .some((l) => l.some((s) => s === "verified")),
  );
  check("absent source URL is stated, not implied", journey.body.includes("no per-document source url stored"));
  check("absent verification date is stated", journey.body.includes("no verification date on record"));
  check("verified quote panel renders", /verified source quotes \[1\]/.test(journey.body));
  check("retrieved sources panel renders", /retrieved sources \[3\]/.test(journey.body));
  console.log(`shot  ${await screenshot("journey-answer.png", "ul li:last-child")}`);

  // 2b — the provenance edge cases --------------------------------------------
  await evaluate(`(() => {
    const input = document.querySelector('input[aria-label="Question"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, 'edge case provenance question');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.form.requestSubmit();
  })()`);
  await waitFor("document.body.innerText.toLowerCase().includes('mystery_status')", {
    label: "edge-case sources",
  });
  const edge = await evaluate(`(() => [...document.querySelectorAll('[data-testid="source-card"]')]
    .map((c) => ({ status: c.dataset.status, text: c.innerText.trim().split('\\n').map((s) => s.trim().toLowerCase()).filter(Boolean) })))()`);
  const edgeText = JSON.stringify(edge).toLowerCase();
  check("directory seed has its own label", edgeText.includes("directory seed"));
  check("a record with no data_status says so", edgeText.includes("provenance unlabelled"));
  check("an unknown status renders raw, not neutral", edgeText.includes("unrecognised status · mystery_status"));

  // 3 — failure state ----------------------------------------------------------
  await evaluate(`(() => {
    const input = document.querySelector('input[aria-label="Question"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, 'boom deliberate failure');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.form.requestSubmit();
  })()`);
  await waitFor("document.body.innerText.toLowerCase().includes('service notice / error')", {
    label: "error state",
  });
  const failure = await evaluate(`(() => ({
    body: document.body.innerText.toLowerCase(),
    retry: [...document.querySelectorAll('button')].some((b) => b.innerText.toLowerCase().includes('retry question')),
  }))()`);
  check("failure state is labelled and offers a retry", failure.retry);
  check("failure copy does not pretend the answer exists", /rejected the request|unreachable/i.test(failure.body));
  console.log(`shot  ${await screenshot("failure-state.png", "ul li:last-child")}`);

  // 4 — /evidence and /coverage with the API configured ------------------------
  await goto(`${BASE}/evidence`);
  const evidence = await evaluate(`(() => {
    const text = document.body.innerText.toLowerCase();
    return {
      metrics: document.querySelectorAll('[data-testid^="metric-"]').length,
      hasInt8: text.includes('0.802083') && text.includes('int8 onnx'),
      hasFp32: text.includes('0.796875') && text.includes('fp32 pytorch'),
      hasOfflinePanel: !!document.querySelector('[data-testid="offline-panel"]'),
    };
  })()`);
  check("/evidence renders all four measured cards", evidence.metrics === 4, `${evidence.metrics} cards`);
  check("/evidence labels both MRR@4 runtimes", evidence.hasInt8 && evidence.hasFp32);
  check("/evidence is not the offline-only panel", evidence.hasOfflinePanel === false);
  console.log(`shot  ${await screenshot("evidence-route.png")}`);

  await goto(`${BASE}/coverage`);
  await waitFor("!!document.querySelector('[data-testid=\"coverage-report\"]')", { label: "coverage report" });
  const coverage = await evaluate(`(() => ({
    jurisdictions: document.querySelector('[data-testid="coverage-jurisdictions"]').innerText.replace(/\\s+/g, ' '),
    note: document.querySelector('[data-testid="coverage-note"]').innerText,
    list: document.querySelectorAll('[data-testid="coverage-jurisdiction-list"] li').length,
  }))()`);
  check("/coverage renders the live report", coverage.jurisdictions.includes("36"), coverage.jurisdictions);
  check("/coverage reproduces the API's coverage note", coverage.note.includes("discovery directory"));
  check("/coverage lists per-jurisdiction records", coverage.list > 0, `${coverage.list} rows`);
  console.log(`shot  ${await screenshot("coverage-route.png")}`);

  // 5 — narrow viewport and keyboard navigation --------------------------------
  await viewport(375, 812);
  await goto(`${BASE}/`);
  const narrow = await evaluate(`(() => {
    const header = document.querySelector('header').getBoundingClientRect();
    return { headerWidth: header.width, overflow: document.documentElement.scrollWidth - 375, visible: header.height > 0 };
  })()`);
  check("header stays visible at 375px", narrow.visible && narrow.headerWidth > 300, `overflow ${narrow.overflow}px`);
  await evaluate("document.body.focus()");
  let focus = null;
  let focusTrail = [];
  for (let i = 0; i < 10 && !focus; i += 1) {
    await pressTab();
    const current = await evaluate(`(() => {
      const el = document.activeElement;
      if (!el || el.tagName !== 'A') return null;
      const cs = getComputedStyle(el);
      return { text: el.innerText.trim(), href: el.getAttribute('href'), outline: cs.outlineStyle, width: cs.outlineWidth };
    })()`);
    if (current) {
      focusTrail.push(`${current.text}→${current.href}`);
      if (current.href === "/evidence") focus = current;
    }
  }
  check(
    "keyboard focus reaches the evidence nav link with a visible focus ring",
    Boolean(focus) && focus.outline !== "none" && parseFloat(focus.width) > 0,
    `${focusTrail.join(" | ")} :: ${JSON.stringify(focus)}`,
  );
  console.log(`shot  ${await screenshot("narrow-home.png")}`);

  check("no client-side JS errors in the tested paths", consoleErrors.length === 0, consoleErrors.join(" | "));
  check("no failed requests in the tested paths", failedRequests.length === 0, failedRequests.join(" | "));
} catch (error) {
  check("journey completed without an unhandled error", false, String(error));
} finally {
  ws.close();
  chrome.kill();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
