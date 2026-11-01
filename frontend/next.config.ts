import type { NextConfig } from "next";

// The browser talks to same-origin /api/*; Next.js proxies it to the FastAPI backend so
// authentication cookies stay first-party. BACKEND_URL is a server-side setting; a bare host
// ("api.example.com") is accepted and treated as https.
const rawBackend = (process.env.BACKEND_URL ?? "").trim() || "http://localhost:8000";
const backend = (/^https?:\/\//.test(rawBackend) ? rawBackend : `https://${rawBackend}`).replace(/\/+$/, "");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self)" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
