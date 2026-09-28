import {
  BackendTaskResponse,
  BackendTimelineResponse,
  BackendFileUploadResponse,
  BackendKnowledgeUploadResponse,
  BackendKnowledgeStatusResponse,
  BackendModelsResponse,
  BackendSovereigntyResponse,
  BackendPIDAnalyzeResponse,
  BackendReadyzResponse,
} from "@/types/workbench"
import { SseFrameParser, isTerminalEvent } from "@/lib/sse"

/**
 * Intentionally empty. Every request this client makes is same-origin and relative.
 *
 * This is a deliberate air-gap decision, not an oversight and not something to
 * "fix" by pointing it at `http://127.0.0.1:8000` (Frontend-fix.md item 3.5).
 *
 * The backend is reached through the same-origin proxy at `app/api/[...path]/route.ts`,
 * which forwards server-side using the server-only `BACKEND_ORIGIN` in
 * `lib/backend-origin.ts`. That gives three properties that a direct browser-to-backend
 * call cannot:
 *
 *   1. The backend's address never enters a client bundle. It is read from
 *      `process.env` in a server-only module, so it cannot be inlined or leaked.
 *   2. The browser's only network peer is the frontend's own origin. Nothing points at
 *      a second host, which is what the sovereignty claim in the UI actually rests on.
 *   3. `X-Inference-Mode` and the `BACKEND_UNREACHABLE` envelope are observable in one
 *      place instead of being duplicated per call site.
 *
 * The consequence to be aware of: this only works while the browser talks to the
 * Next.js server. It is not a base URL you can repoint at a different backend from the
 * client, and that is on purpose -- doing so would put a second origin in the bundle
 * and require backend CORS to admit it. To change which backend is used, set
 * `BACKEND_URL` in the server's environment (see `.env.example`), not here.
 */
const API_BASE = ""

/**
 * The inference mode reported by the backend on its most recent response.
 *
 * Per AGENTS.md G6, `app/main.py:116` sets `X-Inference-Mode: <mode>` on **every**
 * response, and `tests/integration/test_inference_mode_reporting.py` asserts that the
 * header, `active_inference_mode` on `/api/models` and `inference_mode` on
 * `/api/monitoring/sovereignty` all agree. The header is therefore the authoritative
 * source — it is the one value the backend states unconditionally, and it needs no
 * second request to corroborate.
 *
 * The frontend previously ignored it and re-derived mode from two endpoints that can
 * disagree, with `??` fallbacks that failed *open* to `"groq"` and
 * `"groq_endpoint_only"`. See Frontend-fix.md item 2.5.
 *
 * `null` means no response has been observed yet, or none carried the header.
 */
let reportedInferenceMode: "local" | "groq" | null = null

export function getReportedInferenceMode(): "local" | "groq" | null {
  return reportedInferenceMode
}

/** Record the mode from a response. Ignores anything that is not `local` or `groq`. */
function observeInferenceMode(res: Response): void {
  const mode = res.headers?.get("X-Inference-Mode")
  if (mode === "local" || mode === "groq") {
    reportedInferenceMode = mode
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  // Observed before the ok-check: the header is present on error responses too, so a
  // failed call still tells us which mode the backend is running in.
  observeInferenceMode(res)
  if (!res.ok) {
    let code = "UNKNOWN_ERROR"
    let message = `Request failed with status ${res.status}`
    let requestId: string | undefined
    try {
      const errJson = await res.json()
      if (errJson.error) {
        code = errJson.error.code || code
        message = errJson.error.message || message
        requestId = errJson.error.request_id
      }
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, code, message, requestId)
  }
  return res.json() as Promise<T>
}

export interface ChatStreamEvent {
  id?: string
  type: string
  data: Record<string, unknown>
}

export const apiClient = {
  /**
   * Health and readiness checks
   */
  async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/healthz`, { cache: "no-store" })
      // /healthz bypasses handleResponse, so observe the header here too — it is
      // typically the first request the app makes and therefore the first evidence of
      // which mode the backend is actually in.
      observeInferenceMode(res)
      if (!res.ok) return false
      const data = await res.json()
      return data.ok === true
    } catch {
      return false
    }
  },

  async checkReady(): Promise<BackendReadyzResponse | null> {
    try {
      const res = await fetch(`${API_BASE}/readyz`, { cache: "no-store" })
      observeInferenceMode(res)
      if (!res.ok) return null
      return await res.json()
    } catch {
      return null
    }
  },

  /**
   * Real-time monitoring
   */
  async getSovereignty(): Promise<BackendSovereigntyResponse> {
    const res = await fetch(`${API_BASE}/api/monitoring/sovereignty`, {
      cache: "no-store",
    })
    return handleResponse<BackendSovereigntyResponse>(res)
  },

  /**
   * Models status and hardware profile
   */
  async getModels(): Promise<BackendModelsResponse> {
    const res = await fetch(`${API_BASE}/api/models`, {
      cache: "no-store",
    })
    return handleResponse<BackendModelsResponse>(res)
  },

  async setActiveModel(modelId: string): Promise<{ status: string; active_model_id: string }> {
    const res = await fetch(`${API_BASE}/api/models/active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    })
    return handleResponse<{ status: string; active_model_id: string }>(res)
  },

  /**
   * Register a custom model (app/api/models.py -> RegisterModelRequest).
   *
   * Only the fields the backend actually declares are sent. Omitted fields are filled
   * in by the server's pydantic defaults (paramCount "70B", quantization "Q4_K_M",
   * speedTokSec 30.0, contextLength 32768), so anything not supplied here must not be
   * displayed as though the user or the system had measured it.
   */
  async registerModel(payload: {
    id: string
    name: string
    role?: string
    tasks?: string[]
  }): Promise<{ status: string; model: Record<string, unknown> }> {
    const res = await fetch(`${API_BASE}/api/models`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    return handleResponse<{ status: string; model: Record<string, unknown> }>(res)
  },

  /**
   * Task retrieval and timeline
   */
  async listTasks(limit: number = 50): Promise<{ tasks: BackendTaskResponse[] }> {
    const res = await fetch(`${API_BASE}/api/tasks?limit=${limit}`, {
      cache: "no-store",
    })
    return handleResponse<{ tasks: BackendTaskResponse[] }>(res)
  },

  async getTask(taskId: string): Promise<BackendTaskResponse> {
    const res = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
      cache: "no-store",
    })
    return handleResponse<BackendTaskResponse>(res)
  },

  async getTimeline(taskId: string): Promise<BackendTimelineResponse> {
    const res = await fetch(`${API_BASE}/api/tasks/${taskId}/timeline`, {
      cache: "no-store",
    })
    return handleResponse<BackendTimelineResponse>(res)
  },

  async getAllTimeline(): Promise<BackendTimelineResponse> {
    const res = await fetch(`${API_BASE}/api/tasks/timeline/all`, {
      cache: "no-store",
    })
    return handleResponse<BackendTimelineResponse>(res)
  },

  /**
   * Human-in-the-loop approval gate
   */
  async approveTask(
    taskId: string,
    approver: string,
    decision: "approve" | "reject",
    note?: string
  ): Promise<{ task_id: string; current_state: string; approved_by: string }> {
    const res = await fetch(`${API_BASE}/api/tasks/${taskId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approver, decision, note }),
    })
    return handleResponse(res)
  },

  /**
   * Files and Knowledge listings
   */
  async listFiles(): Promise<BackendFileUploadResponse> {
    const res = await fetch(`${API_BASE}/api/files`, {
      cache: "no-store",
    })
    return handleResponse<BackendFileUploadResponse>(res)
  },

  async listKnowledge(): Promise<BackendKnowledgeUploadResponse> {
    const res = await fetch(`${API_BASE}/api/knowledge`, {
      cache: "no-store",
    })
    return handleResponse<BackendKnowledgeUploadResponse>(res)
  },

  /**
   * Upload general files
   */
  async uploadFiles(files: File[], taskId?: string): Promise<BackendFileUploadResponse> {
    const formData = new FormData()
    for (const f of files) {
      formData.append("file", f)
    }
    if (taskId) {
      formData.append("task_id", taskId)
    }
    const res = await fetch(`${API_BASE}/api/files/upload`, {
      method: "POST",
      body: formData,
    })
    return handleResponse<BackendFileUploadResponse>(res)
  },

  /**
   * Knowledge RAG upload and indexing status
   */
  async uploadKnowledge(files: File[]): Promise<BackendKnowledgeUploadResponse> {
    const formData = new FormData()
    for (const f of files) {
      formData.append("file", f)
    }
    const res = await fetch(`${API_BASE}/api/knowledge/upload`, {
      method: "POST",
      body: formData,
    })
    return handleResponse<BackendKnowledgeUploadResponse>(res)
  },

  async getKnowledgeStatus(fileId: string): Promise<BackendKnowledgeStatusResponse> {
    const res = await fetch(`${API_BASE}/api/knowledge/${fileId}`, {
      cache: "no-store",
    })
    return handleResponse<BackendKnowledgeStatusResponse>(res)
  },

  /**
   * Artifacts
   *
   * The returned URL is intentionally relative (Frontend-fix.md 3.5): artifact bytes
   * are only ever fetched same-origin through the `/api/*` proxy, exactly like every
   * other call in this client. Under a direct backend origin this relative URL would
   * resolve against the page's own host rather than the backend -- which is correct,
   * because pointing the browser at the backend directly is not a supported
   * deployment; the server-side origin is the one `BACKEND_URL` names. See the
   * comment on `API_BASE` above for why that arrangement exists in the first place.
   */
  getArtifactDownloadUrl(artifactId: string): string {
    return `${API_BASE}/api/artifacts/${artifactId}?download=1`
  },

  async getArtifactManifest(artifactId: string): Promise<Record<string, unknown>> {
    const res = await fetch(`${API_BASE}/api/artifacts/${artifactId}`, {
      cache: "no-store",
    })
    return handleResponse<Record<string, unknown>>(res)
  },

  /**
   * P&ID Image analysis
   */
  async analyzePID(file: File): Promise<BackendPIDAnalyzeResponse> {
    const formData = new FormData()
    formData.append("file", file)
    const res = await fetch(`${API_BASE}/api/pid/analyze`, {
      method: "POST",
      body: formData,
    })
    return handleResponse<BackendPIDAnalyzeResponse>(res)
  },

  /**
   * Real-time Chat SSE Stream
   * Initiates POST /api/chat and consumes Server-Sent Events via ReadableStream
   */
  async chatStream(
    message: string,
    options?: {
      fileIds?: string[]
      knowledgeIds?: string[]
      onEvent?: (event: ChatStreamEvent) => void
      onTaskId?: (taskId: string) => void
      signal?: AbortSignal
    }
  ): Promise<{ taskId: string }> {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        message,
        file_ids: options?.fileIds || [],
        knowledge_ids: options?.knowledgeIds || [],
      }),
      signal: options?.signal,
    })

    if (!res.ok) {
      return handleResponse(res)
    }

    // The SSE path never reaches handleResponse on success, so observe the header
    // here as well.
    observeInferenceMode(res)

    const taskId = res.headers.get("X-Task-Id") || ""
    if (taskId && options?.onTaskId) {
      options.onTaskId(taskId)
    }

    if (!res.body) {
      return { taskId }
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    const parser = new SseFrameParser()

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
          options?.onEvent?.(frame)
          if (isTerminalEvent(frame.type)) return { taskId }
        }
      }
      for (const frame of parser.flush()) options?.onEvent?.(frame)
    } finally {
      reader.releaseLock()
    }

    return { taskId }
  },

  /**
   * Reattach to a task's event stream, replaying everything after `lastEventId`
   * (Frontend-fix.md item 2.1).
   *
   * `GET /api/tasks/{id}/stream` (`app/api/tasks.py:31-46`) reads the `Last-Event-Id`
   * header, coerces it to an int, and calls `bus.subscribe(task_id, after)`, which
   * replays persisted events with `id > after` and then follows live. That is what
   * makes a resume gapless: a client that has seen up to id 42 receives 43 onward,
   * with no duplicate and no gap.
   *
   * Passing `undefined` replays from the beginning, which is the correct behaviour
   * when there is no recorded position (a first-ever resume, or cleared storage).
   *
   * `EventSource` is deliberately not used. It re-connects on its own and cannot send
   * `Last-Event-Id` on the *initial* connection, which is the one that matters here.
   * The manual reader below is the same mechanism `chatStream` uses.
   */
  async resumeStream(
    taskId: string,
    lastEventId: string | number | undefined,
    options?: {
      onEvent?: (event: ChatStreamEvent) => void
      signal?: AbortSignal
    }
  ): Promise<void> {
    const headers: Record<string, string> = { Accept: "text/event-stream" }
    if (lastEventId !== undefined && lastEventId !== null && lastEventId !== "") {
      headers["Last-Event-Id"] = String(lastEventId)
    }

    const res = await fetch(
      `${API_BASE}/api/tasks/${encodeURIComponent(taskId)}/stream`,
      { headers, cache: "no-store", signal: options?.signal }
    )

    if (!res.ok) {
      let code = "STREAM_RESUME_FAILED"
      let message = `Could not resume the event stream (HTTP ${res.status})`
      try {
        const errJson = await res.json()
        if (errJson?.error) {
          code = errJson.error.code || code
          message = errJson.error.message || message
        }
      } catch {
        // not JSON
      }
      throw new ApiError(res.status, code, message)
    }
    observeInferenceMode(res)

    if (!res.body) return

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    const parser = new SseFrameParser()
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
          options?.onEvent?.(frame)
          if (isTerminalEvent(frame.type)) return
        }
      }
      for (const frame of parser.flush()) options?.onEvent?.(frame)
    } finally {
      reader.releaseLock()
    }
  },
}
