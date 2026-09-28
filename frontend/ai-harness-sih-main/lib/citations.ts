import { SOPCitation } from "@/types/workbench"

/**
 * Map a backend retrieval chunk to a citation.
 *
 * Chunks arrive as `{chunk_id, document_id, page, section, source_hash, text}`
 * (see the `retrieval` event in AGENTS.md G9). Anything the backend did not send is
 * omitted rather than filled in: a citation must never name a document, section or
 * confidence score that the system did not actually retrieve.
 *
 * There is deliberately no "SOP-ENG-042"-style fallback. A plausible-looking citation
 * to a document that was never retrieved is worse than no citation at all.
 */
export function mapChunkToCitation(
  chunk: unknown,
  index: number,
  scope: string
): SOPCitation | null {
  if (!chunk || typeof chunk !== "object") return null
  const c = chunk as Record<string, unknown>

  const chunkId = str(c.chunk_id)
  const documentId = str(c.document_id)
  const text = str(c.text) ?? str(c.snippet)

  // Without an identifier or any text there is nothing to cite.
  if (!chunkId && !documentId && !text) return null

  const id = chunkId ?? documentId ?? `chunk-${index}`
  const section = str(c.section)

  return {
    id: `cit-${index}-${scope}`,
    source: id,
    title: documentId ?? id,
    ...(section ? { section } : {}),
    ...(typeof c.page === "number" ? { page: c.page } : {}),
    snippet: text ?? "",
    ...(typeof c.score === "number" ? { confidence: c.score } : {}),
    ...(c.tolerance !== undefined && c.tolerance !== null
      ? { toleranceRequired: String(c.tolerance) }
      : {}),
  }
}

/** Map a `retrieval` event's chunk array, dropping entries that cannot be cited. */
export function mapChunksToCitations(chunks: unknown, scope: string): SOPCitation[] {
  if (!Array.isArray(chunks)) return []
  return chunks
    .map((chunk, i) => mapChunkToCitation(chunk, i, scope))
    .filter((c): c is SOPCitation => c !== null)
}

function str(v: unknown): string | undefined {
  if (typeof v === "string" && v.trim()) return v
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return undefined
}
