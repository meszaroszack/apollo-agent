import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // NEXT_PUBLIC_* vars are baked in at build time via Dockerfile ARGs
  // Fallback to localhost only for local dev
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000",
  },
};

export default nextConfig;
