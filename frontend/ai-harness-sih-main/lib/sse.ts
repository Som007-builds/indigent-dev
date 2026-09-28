/**
 * One SSE frame parser, shared by both stream paths.
 *
 * There are two ways this client consumes `text/event-stream`:
 *
 *   * `POST /api/chat` — starts a task and streams it (the original path)
 *   * `GET /api/tasks/{id}/stream` — resumes an existing task, honouring
 *     `Last-Event-ID` (added for Frontend-fix.md item 2.1)
 *
 * Both speak the identical wire format, so they must not have two parsers: the day
 * they disagree, a resumed task silently loses the event the live path handled, and
 * the bug is invisible until a refresh happens mid-run. Same reasoning as
 * `lib/citations.ts`.
 *
 * Wire format, as produced by `app/api/tasks.py:40-44`:
 *
 *   id: 42
 *   event: state_changed
 *   data: {"id":42,"task_id":"…","ts":"…","type":"state_changed",
 *          "inference_mode":"local","data":{…}}
 *
 * `data:` is the **whole envelope**, so the event's own payload is `envelope.data`.
 * `EventSourceResponse(..., ping=15)` also emits `:` comment lines as keep-alives;
 * those carry no `id:`/`event:`/`data:` and are correctly ignored, which is what
 * keeps an idle stream from being mistaken for progress.
 */

export interface SseFrame {
  /** The `id:` field. Empty string when the frame omitted one. */
  id: string
  type: string
  /** The event's payload — `envelope.data`, not the envelope. */
  data: Record<string, unknown>
}

export class SseFrameParser {
  private buffer = ""
  private currentEvent = "message"
  private currentId = ""
  private currentData = ""

  /**
   * Feed a decoded chunk. Returns every frame that became complete, which may be none,
   * one, or several if the chunk contained multiple frames.
   */
  push(chunk: string): SseFrame[] {
    this.buffer += chunk
    const frames: SseFrame[] = []
    const lines = this.buffer.split("\n")
    // The final element is an incomplete line; hold it for the next chunk.
    this.buffer = lines.pop() ?? ""

    for (const line of lines) {
      const frame = this.consumeLine(line)
      if (frame) frames.push(frame)
    }
    return frames
  }

  /**
   * Emit a trailing frame that arrived without its terminating blank line. A stream
   * cut mid-frame would otherwise be dropped silently, which on resume is exactly the
   * "one skipped event" failure item 2.1 is meant to prevent.
   */
  flush(): SseFrame[] {
    const frame = this.emit()
    this.buffer = ""
    return frame ? [frame] : []
  }

  private consumeLine(line: string): SseFrame | null {
    const trimmed = line.trim()
    if (!trimmed) return this.emit()
    // A line starting with ':' is an SSE comment, used here for keep-alive pings.
    if (trimmed.startsWith(":")) return null

    if (trimmed.startsWith("event:")) {
      this.currentEvent = trimmed.slice(6).trim()
    } else if (trimmed.startsWith("id:")) {
      this.currentId = trimmed.slice(3).trim()
    } else if (trimmed.startsWith("data:")) {
      const dataLine = trimmed.slice(5).trim()
      this.currentData = this.currentData ? `${this.currentData}\n${dataLine}` : dataLine
    }
    return null
  }

  private emit(): SseFrame | null {
    if (!this.currentData) {
      this.reset()
      return null
    }
    let type = this.currentEvent
    let data: Record<string, unknown>
    try {
      const parsed: unknown = JSON.parse(this.currentData)
      if (parsed && typeof parsed === "object") {
        const envelope = parsed as { type?: unknown; data?: unknown }
        // The envelope's own `type` is authoritative when the `event:` field is the
        // generic default the backend emits.
        if (type === "message" && typeof envelope.type === "string") {
          type = envelope.type
        }
        data =
          envelope.data && typeof envelope.data === "object"
            ? (envelope.data as Record<string, unknown>)
            : (parsed as Record<string, unknown>)
      } else {
        data = { raw: String(parsed) }
      }
    } catch {
      // Not JSON. Surface it rather than dropping the frame: a payload we cannot
      // parse is a fact about the backend worth showing.
      data = { raw: this.currentData }
    }
    const frame: SseFrame = { id: this.currentId, type, data }
    this.reset()
    return frame
  }

  private reset(): void {
    this.currentEvent = "message"
    this.currentId = ""
    this.currentData = ""
  }
}

/**
 * States after which the backend closes the stream (G9: `completed` and `failed` are
 * terminal). A resume must stop at these too, or it will hold a connection open
 * against a task that will never produce another event.
 */
export function isTerminalEvent(type: string): boolean {
  return type === "completed" || type === "failed"
}
