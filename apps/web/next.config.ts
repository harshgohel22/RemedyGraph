import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://localhost:3000"],
  async rewrites() {
    const explicit = process.env.API_PROXY?.replace(/\/$/, "");
    if (explicit) {
      return [{ source: "/v1/:path*", destination: `${explicit}/v1/:path*` }];
    }
    if (process.env.NODE_ENV !== "production") {
      return [{ source: "/v1/:path*", destination: "http://127.0.0.1:8000/v1/:path*" }];
    }
    return [];
  },
};

export default nextConfig;
