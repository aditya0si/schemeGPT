import type { NextConfig } from "next";

// Conservative, nonce-free response-header policy (security finding F1).
//
// It is deliberately a *static* header set delivered from the Next config
// rather than middleware: config headers also cover prerendered routes such as
// /evidence, cost no per-request invocation, and need no nonce plumbing.
// What each directive does and does not buy, and the headers deliberately
// rejected, are pinned by tests/test_web_security_headers.py and asserted
// against a real production build by web/e2e/csp.mjs.
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  // Next's App Router delivers the RSC flight payload as inline
  // <script>self.__next_f.push(...)</script>. A bare 'self' blanks the page, so
  // 'unsafe-inline' is required. That means script-src does NOT mitigate XSS
  // here; its value is blocking script from any third-party origin, and CSP3
  // ignores 'unsafe-inline' the moment a nonce or hash appears, so a later
  // nonce migration stiffens this without a second edit.
  "script-src 'self' 'unsafe-inline'",
  // Tailwind and next/font emit inline <style> on the server render path.
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  // next/font self-hosts the woff2 files under /_next/static/media.
  "font-src 'self' data:",
  // The browser only ever talks to this origin: API_URL is server-side and no
  // NEXT_PUBLIC_* variable exists, so /api/* proxies to the Python API.
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CONTENT_SECURITY_POLICY },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // The clickjacking pair: frame-ancestors is the modern control, XFO covers
  // engines that never implemented CSP Level 2. Both are asserted, not one.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Every feature the app does not use is denied; the app needs none of them.
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  // Drop the version fingerprint from every response.
  poweredByHeader: false,
  turbopack: {
    // Keep output-file tracing scoped to the web app even when a developer has
    // an unrelated package-lock.json in a parent directory.
    root: process.cwd(),
  },
  async headers() {
    // "/(.*)" matches every route shape: prerendered pages, dynamic pages and
    // route handlers alike, so a static /evidence cannot drift out of policy.
    return [{ source: "/(.*)", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
