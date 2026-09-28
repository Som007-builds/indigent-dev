/**
 * Streaming reverse proxy for every `/api/*` call.
 *
 * ## Why this exists instead of a `rewrites()` entry
 *
 * `next.config.ts` used to proxy `/api/:path*` with a rewrite. That was measured on
 * 2026-09-28 against a live backend and it does not work: the rewrite delivered the
 * response *headers* immediately and then **zero body bytes**, for as long as the
 * stream stayed open.
 *
 * The measurement, same request twice:
 *
 *   direct  127.0.0.1:8000   16 chunks, first byte at 0.83s, frame ids 300-312,
 *                            arrival times 0.83 0.93 1.05 ... 2.34 then keep-alives
 *                            at 15.8 / 30.9 / 45.8  -> genuinely progressive
 *   proxied 127.0.0.1:3000    0 chunks, 0 frame ids, 40s  -> nothing, ever
 *
 * The body did eventually come out, but only when the client disconnected: `curl
 * --max-time 25` received all 3331 bytes at teardown. So the proxy buffers the whole
 * response and flushes on close. For a normal request that is invisible. For
 * `text/event-stream` it means the UI shows no progress for the entire task and then
 * dumps every event at once, which defeats the point of a live event feed and makes
 * the "streaming" claim false.
 *
 * A filesystem route takes precedence over `rewrites()`, so adding this file changes
 * the behaviour of every `/api/*` request at once. `/healthz` and `/readyz` are left
 * on the rewrite: they are small, non-streaming, and verified working there.
 *
 * ## The two rules that make it stream
 *
 * 1. The upstream body is never read. `upstream.body` is handed straight to the
 *    `Response`, so bytes are relayed as they arrive. Anything that awaited
 *    `res.text()` or `res.json()` would reintroduce the bug.
 * 2. `accept-encoding: identity` on the way out. Node's `fetch` transparently decodes
 *    a compressed upstream body, so forwarding the client's `accept-encoding` would
 *    return a `content-encoding` header describing a body that has already been
 *    decompressed. Both `content-encoding` and `content-length` are therefore dropped
 *    from the response rather than passed through as lies.
 */

import { BACKEND_ORIGIN, STREAMING_RESPONSE_HEADERS } from "@/lib/backend-origin"

export const runtime = "nodejs"
/** Never cache or statically optimize: every one of these is a live backend call. */
export const dynamic = "force-dynamic"

/**
 * Connection-scoped headers that must not be forwarded in either direction, per
 * RFC 9110 7.6.1. `host` and `content-length` are included because Node recomputes
 * both for the new hop.
 */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "content-encoding",
])

/** Forward the client's request headers, minus hop-by-hop and compression. */
function requestHeaders(source: Headers): Headers {
  const headers = new Headers()
  source.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value)
  })
  headers.set("accept-encoding", "identity")
  return headers
}

/**
 * Rebuild the response headers. Status and body are the upstream's; every header the
 * client reads for correctness — `X-Task-Id`, `X-Inference-Mode`, `X-Request-ID`,
 * `Content-Type` — is preserved, because several UI decisions depend on them.
 */
function responseHeaders(source: Headers, streaming: boolean): Headers {
  const headers = new Headers()
  source.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value)
  })
  for (const [key, value] of Object.entries(STREAMING_RESPONSE_HEADERS)) {
    headers.set(key, value)
  }
  if (streaming) headers.set("connection", "keep-alive")
  return headers
}

/**
 * A failure to reach the backend is returned in the backend's own error-envelope
 * shape (`{"error": {code, message, request_id}}`, G11) so `handleResponse` in
 * `lib/api-client.ts` parses it like any other failure. Without this, an unreachable
 * backend would surface to the UI as an opaque proxy error, and the fail-closed
 * behaviour added in items 1.7 and 1.8 would never trigger.
 */
function unreachable(detail: string): Response {
  return new Response(
    JSON.stringify({
      error: {
        code: "BACKEND_UNREACHABLE",
        message: `The backend at ${BACKEND_ORIGIN} could not be reached: ${detail}`,
        request_id: "proxy-generated",
      },
    }),
    { status: 502, headers: { "content-type": "application/json" } }
  )
}

async function proxy(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
): Promise<Response> {
  const { path } = await context.params
  const incoming = new URL(request.url)

  // `path.join("/")` is safe here: these segments are already URL-decoded path
  // segments matched by the filesystem router, and the backend re-validates every id.
  const suffix = (path ?? []).join("/")
  const target = `${BACKEND_ORIGIN}/api/${suffix}${incoming.search}`

  const hasBody = request.method !== "GET" && request.method !== "HEAD"
  // Stream the request body through untouched so multipart uploads (P&ID images up
  // to 25 MB, documents up to 50 MB) are never buffered in memory here.
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: requestHeaders(request.headers),
    redirect: "manual",
    cache: "no-store",
  }
  if (hasBody) {
    init.body = request.body
    // Required by Node's undici when a request body is a stream.
    init.duplex = "half"
  }

  let upstream: Response
  try {
    upstream = await fetch(target, init)
  } catch (error) {
    return unreachable(error instanceof Error ? error.message : String(error))
  }

  const streaming = (upstream.headers.get("content-type") ?? "").includes(
    "text/event-stream"
  )

  // `upstream.body` is passed straight through. Do not buffer it: that is the exact
  // defect this route exists to fix.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream.headers, streaming),
  })
}

// Only the two methods the documented API contract uses (G11). Exporting the others
// would be dead surface: there is no PUT, PATCH or DELETE route on the backend, and
// no browser preflight is involved because the browser only ever talks to Next.
export const GET = proxy
export const POST = proxy
