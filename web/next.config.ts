import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    // Keep output-file tracing scoped to the web app even when a developer has
    // an unrelated package-lock.json in a parent directory.
    root: process.cwd(),
  },
};

export default nextConfig;
