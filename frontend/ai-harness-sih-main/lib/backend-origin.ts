/**
 * The backend origin, for the server-side proxy in `app/api/[...path]/route.ts`.
 *
 * Server-only. It reads `process.env` at request time, so nothing here can be
 * inlined into a client bundle and the backend address is never exposed to the
 * browser — which matters for an air-gapped product, where the whole point is that
 * the only network peer is one specific address on the loopback interface.
 *
 * The default matches the one in `next.config.ts`, which uses the same variable for
 * the `/healthz` and `/readyz` rewrites. Keep the two in step.
 */
export const BACKEND_ORIGIN = (
  process.env.BACKEND_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "")

/**
 * SSE frames are only useful if they arrive while the task is running.
 *
 * `no-transform` forbids any intermediary from buffering or re-encoding the body, and
 * `x-accel-buffering: no` disables nginx-style response buffering. Neither is a
 * substitute for the route handler itself -- they are here because the rewrite that
 * used to sit in `next.config.ts` buffered the entire stream regardless.
 */
export const STREAMING_RESPONSE_HEADERS: Record<string, string> = {
  "cache-control": "no-store, no-transform",
  "x-accel-buffering": "no",
}
