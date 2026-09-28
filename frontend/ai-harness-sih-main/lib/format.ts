/**
 * Display formatting for values the backend sent.
 *
 * The single rule behind this module is the one the whole remediation rests on: never
 * display a value the backend did not send. Where a value is genuinely absent, the
 * honest rendering is a label saying so, not a plausible-looking substitute.
 */

/**
 * The label used wherever the backend reported nothing for a field.
 *
 * One constant, because the alternative is the same twelve characters retyped in four
 * places, and they drift: item 1.13 had a file's Category read "Workspace" and item
 * 1.15 had a model's name read "Groq Model" in exactly that situation. Same underlying
 * mistake, two different invented labels.
 */
export const NOT_REPORTED = "Not reported"

/**
 * Format a byte count for display, e.g. `1536` -> `"1.5 KB"`.
 *
 * Returns {@link NOT_REPORTED} for a missing or nonsensical size. A real zero-byte
 * file renders as `"0 B"`, which is a fact; `null` renders as not reported, which is
 * the absence of one. Collapsing the two would be its own small lie, and the reason
 * this function does not just do `String(bytes ?? 0)`.
 */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) {
    return NOT_REPORTED
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ["KB", "MB", "GB", "TB"]
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  // One decimal below 100, none above: "9.4 MB" is useful, "128.0 MB" is noise.
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`
}
