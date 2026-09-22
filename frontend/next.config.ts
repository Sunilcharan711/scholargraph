import type { NextConfig } from "next";
const config: NextConfig = {
  output: process.env.BUILD_STANDALONE === "1" ? "standalone" : undefined,
  experimental: {proxyClientMaxBodySize: "26mb", proxyTimeout: 180000},
  async rewrites() { return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*` }]; },
};
export default config;
