import type { NextConfig } from "next";
const config: NextConfig = {
  output: process.env.BUILD_STANDALONE === "1" ? "standalone" : undefined,
  // A comparison row can require four sequential local model calls (120s each).
  experimental: {proxyClientMaxBodySize: "26mb", proxyTimeout: 540000},
  async rewrites() { return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*` }]; },
};
export default config;
