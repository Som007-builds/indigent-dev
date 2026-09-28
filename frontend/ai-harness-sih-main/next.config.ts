import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000"
    return [
      // `/api/*` is deliberately NOT rewritten. It is proxied by
      // `app/api/[...path]/route.ts`, because a rewrite buffers the whole response:
      // measured 2026-09-28, the rewrite delivered the SSE response headers and then
      // zero body bytes until the client disconnected. A filesystem route takes
      // precedence over `rewrites()` anyway, so re-adding this entry would change
      // nothing while reading as though the buffering bug had been fixed here.
      // Do not restore it.
      //
      // These two stay on the rewrite: small, non-streaming, and verified working.
      {
        source: "/healthz",
        destination: `${backendUrl}/healthz`,
      },
      {
        source: "/readyz",
        destination: `${backendUrl}/readyz`,
      },
    ]
  },
}

export default nextConfig
