"use client"

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react"
import {
  TaskState,
  TaskType,
  SovereigntyMetrics,
  PIDNode,
  AgentStep,
  ArtifactDeliverable,
  ApprovalData,
  RoutingReceipt,
  AgentState,
  BackendTaskResponse,
  BackendArtifactItem,
} from "@/types/workbench"
import { formatBytes } from "@/lib/format"
import {
  apiClient,
  ApiError,
  getReportedInferenceMode,
  type ChatStreamEvent,
} from "@/lib/api-client"
import { mapChunksToCitations } from "@/lib/citations"
import {
  pendingRouting,
  routingFromModelSelected,
  routingFromTaskRecord,
} from "@/lib/routing"

interface WorkbenchContextType {
  activeTask: TaskState | null
  recentTasks: BackendTaskResponse[]
  sovereignty: SovereigntyMetrics
  selectedNode: PIDNode | null
  setSelectedNode: (node: PIDNode | null) => void
  activeTab: string
  setActiveTab: (tab: string) => void
  isContextPanelOpen: boolean
  setIsContextPanelOpen: (open: boolean) => void
  isExpandedView: boolean
  setIsExpandedView: (expanded: boolean) => void
  isBackendConnected: boolean
  isExecuting: boolean
  handleApprove: (approver: string, note?: string) => Promise<void>
  handleReject: (approver: string, note?: string) => Promise<void>
  handleModify: () => Promise<void>
  /** Re-read sovereignty telemetry from the backend. No simulation. */
  refreshSovereignty: () => Promise<void>
  submitMessage: (message: string, attachedFiles?: File[]) => Promise<void>
  loadTask: (taskId: string) => Promise<void>
  refreshRecentTasks: () => Promise<void>
  resetTask: () => void
  activeModelId: string
  setActiveModelId: (modelId: string) => Promise<void>
}

const WorkbenchContext = createContext<WorkbenchContextType | undefined>(undefined)

/**
 * Map backend artifact manifests to UI deliverables.
 *
 * Shared by `loadTask`, the resume path, and the `artifact_created` handler. The
 * `artifact_created` / `artifact_validation` events (G9) carry only
 * `{artifact_id, artifact_type}` — no path, no verification status, no size — so an
 * artifact's real metadata is only ever available from `GET /api/tasks/{id}`. All three
 * paths must read it the same way, so they call this.
 */
function mapManifests(
  manifests: BackendArtifactItem[],
  timestamp: string
): ArtifactDeliverable[] {
  return manifests.map((a) => ({
    id: a.artifact_id,
    filename: a.path.split("/").pop() || `${a.artifact_type}.bin`,
    // `graph_json` is stored as an artifact type but opened as JSON, so this one
    // remapping is a real translation rather than a cast to hide a mismatch.
    fileType: a.artifact_type === "graph_json" ? "json" : a.artifact_type,
    // Real bytes from the backend, formatted for display. This field held the literal
    // string "Validated deliverable" until Frontend-fix.md 3.2 — a statement about the
    // artifact's validity sitting in the field the UI renders as its size.
    fileSizeFormatted: formatBytes(a.size_bytes),
    downloadUrl: apiClient.getArtifactDownloadUrl(a.artifact_id),
    validationStatus: a.verification_status === "passed" ? "validated" : "warning",
    validationMessage: `Validated ${a.artifact_type} structure and sha256 checksum`,
    summary: `Generated deliverable (${a.artifact_type})`,
    generatedAt: timestamp,
  }))
}

/**
 * Narrow an untrusted value to a real `TaskType`.
 *
 * The backend's `task_type` is a plain nullable string column, and `model_selected` /
 * `state_changed` event payloads are untyped dicts, so either could carry something
 * outside G7's three values. Anything unrecognised becomes `null` — unclassified —
 * rather than being passed through into a union it does not belong to, or defaulted
 * to a placeholder that reads as a real classification.
 */
function asTaskType(value: unknown): TaskType | null {
  return value === "inspection" || value === "coding" || value === "pid_analysis"
    ? value
    : null
}

/**
 * Where to resume an interrupted task from (Frontend-fix.md item 2.1).
 *
 * `lastEventId` is the `id:` of the most recent event this client actually applied.
 * `GET /api/tasks/{id}/stream` replays everything with a greater id, so the pair
 * makes a resume gapless: no event seen twice, none skipped.
 */
interface ResumeCursor {
  taskId: string
  lastEventId: string | null
}

const RESUME_STORAGE_KEY = "indigent.resume-cursor.v1"

/**
 * States in which a task can still emit events.
 *
 * `COMPLETE` and `FAILED` are terminal (G9: the stream closes after them). `APPROVAL`
 * is excluded too, and deliberately: it is a *pause*, not an end. The runner is
 * waiting for a human decision, so no further events exist to replay, and opening a
 * stream would sit idle on a task that will only move when someone approves it.
 */
const RESUMABLE_STATES: ReadonlySet<AgentState> = new Set<AgentState>([
  "INTAKE",
  "CLASSIFY",
  "PLAN",
  "RETRIEVE",
  "TOOL",
  "VERIFY",
  "REPAIR",
  "ARTIFACT",
  "ARTIFACT_VALIDATE",
])

/** Surface what the backend actually said, including the error code. */
function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.code} (HTTP ${err.status}): ${err.message}`
  if (err instanceof Error) return err.message
  return "Unknown error"
}

export function WorkbenchProvider({ children }: { children: React.ReactNode }) {
  const [activeTask, setActiveTask] = useState<TaskState | null>(null)
  const [recentTasks, setRecentTasks] = useState<BackendTaskResponse[]>([])
  // Starts UNKNOWN, not "air-gapped". Previously seeded from defaultSovereigntyMetrics,
  // which asserted isAirGapped:true with invented counters (184 local requests,
  // 42 firewall rules) — so the header showed a green pulsing AIR-GAPPED badge before
  // the backend had ever been contacted. See Frontend-fix.md item 1.7.
  const [sovereignty, setSovereignty] = useState<SovereigntyMetrics>({
    statusKnown: false,
    isAirGapped: false,
    internetBlocked: false,
    externalApiCalls: 0,
    externalDnsQueries: 0,
    externalConnections: 0,
    localRequests: 0,
    statusText: "UNKNOWN",
    activeFirewallRules: 0,
  })
  const [selectedNode, setSelectedNode] = useState<PIDNode | null>(null)
  const [activeTab, setActiveTab] = useState<string>("artifacts")
  const [isContextPanelOpen, setIsContextPanelOpen] = useState<boolean>(true)
  const [isExpandedView, setIsExpandedView] = useState<boolean>(false)
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false)
  const [isExecuting, setIsExecuting] = useState<boolean>(false)
  // Unknown until /api/models or a model_selected event supplies one. Was hardcoded
  // to "openai/gpt-oss-120b", so the global header named a specific hosted model on
  // first paint regardless of what was actually loaded.
  const [activeModelId, setActiveModelIdState] = useState<string>("")

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // --- Resume cursor (Frontend-fix.md item 2.1) --------------------------------
  // Refs, not state: the cursor is written on every event and read only when a resume
  // starts, so it must not trigger a re-render per event.
  const cursorTaskIdRef = useRef<string | null>(null)
  const cursorEventIdRef = useRef<string | null>(null)
  /** Guards the mount effect: React StrictMode runs effects twice in development. */
  const resumeAttemptedRef = useRef(false)
  const resumeAbortRef = useRef<AbortController | null>(null)

  const writeCursor = useCallback((taskId: string | null, lastEventId: string | null) => {
    cursorTaskIdRef.current = taskId
    cursorEventIdRef.current = lastEventId
    try {
      if (taskId) {
        const payload: ResumeCursor = { taskId, lastEventId }
        sessionStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(payload))
      } else {
        sessionStorage.removeItem(RESUME_STORAGE_KEY)
      }
    } catch {
      // sessionStorage throws when storage is disabled or the quota is exhausted.
      // Resuming is an enhancement: losing the cursor means "do not resume", never
      // a broken task, so there is nothing to report and nothing to retry.
    }
  }, [])

  const readCursor = useCallback((): ResumeCursor | null => {
    try {
      const raw = sessionStorage.getItem(RESUME_STORAGE_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<ResumeCursor> | null
      if (!parsed || typeof parsed.taskId !== "string" || !parsed.taskId) return null
      return {
        taskId: parsed.taskId,
        lastEventId: typeof parsed.lastEventId === "string" ? parsed.lastEventId : null,
      }
    } catch {
      // Unreadable or corrupt cursor: treat as absent. A malformed cursor must not
      // block the app, and silently starting from 0 is the safe direction.
      return null
    }
  }, [])

  const recordEventId = useCallback(
    (id: string) => {
      // Guard against a replayed frame moving the cursor backwards. The backend
      // replays ascending ids, but a resume racing a live connection could in
      // principle deliver an older frame last; rewinding would re-deliver events.
      const previous = cursorEventIdRef.current
      if (previous !== null && Number(id) <= Number(previous)) return
      writeCursor(cursorTaskIdRef.current, id)
    },
    [writeCursor]
  )

  const refreshRecentTasks = useCallback(async () => {
    try {
      const res = await apiClient.listTasks(20)
      if (res?.tasks) {
        setRecentTasks(res.tasks)
      }
    } catch {
      // ignore if offline
    }
  }, [])

  // Poll backend health, sovereignty telemetry, and task updates
  const checkBackendState = useCallback(async () => {
    try {
      const isHealthy = await apiClient.checkHealth()
      if (isHealthy) {
        setIsBackendConnected(true)

        // Authoritative inference mode, from the header the backend sets on every
        // response (app/main.py:116). checkHealth() above has already observed it, so
        // by this point it is known even though this snapshot does not carry it.
        const headerMode = getReportedInferenceMode()

        const snap = await apiClient.getSovereignty()
        // getSovereignty() also observes the header, so re-read in case it was the
        // first request to carry one.
        const mode = getReportedInferenceMode()

        // Three-way agreement is asserted backend-side by
        // tests/integration/test_inference_mode_reporting.py. If the header and the
        // snapshot disagree here, the UI is looking at a backend that is not
        // self-consistent — surface it rather than silently preferring one.
        const modeConflict =
          headerMode !== null && snap.inference_mode !== undefined && headerMode !== snap.inference_mode
            ? `${headerMode} (X-Inference-Mode) vs ${snap.inference_mode} (/api/monitoring/sovereignty)`
            : null

        setSovereignty((prev) => ({
          ...prev,
          statusKnown: true,
          isAirGapped: snap.status === "AIR-GAPPED",
          internetBlocked: snap.internet_access === "BLOCKED",
          externalApiCalls: snap.external_api_calls ?? 0,
          externalConnections: snap.external_connections ?? 0,
          externalBytesOut: snap.external_bytes_out ?? 0,
          externalBytesIn: snap.external_bytes_in ?? 0,
          deniedConnectionAttempts: snap.denied_connection_attempts ?? 0,
          statusText: snap.status ?? "UNKNOWN",
          ...(snap.provider !== undefined ? { provider: snap.provider } : {}),
          // Header first, snapshot as the fallback. Neither is invented.
          ...(mode !== null
            ? { inferenceMode: mode }
            : snap.inference_mode !== undefined
            ? { inferenceMode: snap.inference_mode }
            : {}),
          ...(snap.network_policy !== undefined ? { networkPolicy: snap.network_policy } : {}),
          ...(modeConflict ? { modeConflict } : {}),
        }))
        const modelsRes = await apiClient.getModels().catch(() => null)
        if (modelsRes?.active_model_id) {
          setActiveModelIdState(modelsRes.active_model_id)
        }
        await refreshRecentTasks()
      } else {
        setIsBackendConnected(false)
        // Telemetry is no longer valid once the backend is unreachable. Marking it
        // unknown stops the last-known values being presented as current, and stops
        // the header showing a stale green AIR-GAPPED badge while offline.
        setSovereignty((prev) => ({ ...prev, statusKnown: false, statusText: "UNKNOWN" }))
      }
    } catch {
      setIsBackendConnected(false)
      setSovereignty((prev) => ({ ...prev, statusKnown: false, statusText: "UNKNOWN" }))
    }
  }, [refreshRecentTasks])

  const setActiveModelId = useCallback(async (modelId: string) => {
    setActiveModelIdState(modelId)
    try {
      await apiClient.setActiveModel(modelId)
    } catch (err) {
      console.warn("Failed to set active model on backend:", err)
    }
  }, [])

  useEffect(() => {
    checkBackendState()
    pollIntervalRef.current = setInterval(checkBackendState, 3500)
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [checkBackendState])

  const resetTask = useCallback(() => {
    setActiveTask(null)
    setActiveTab("artifacts")
    // Drop the resume cursor too. Otherwise starting a fresh task would leave a cursor
    // pointing at the abandoned one, and a later reload would resurrect a task the
    // user explicitly walked away from.
    writeCursor(null, null)
  }, [writeCursor])

  const loadTask = useCallback(async (taskId: string) => {
    try {
      const task = await apiClient.getTask(taskId)
      const nowTime = task.created_at ? new Date(task.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })

      const mappedSteps: AgentStep[] = []
      mappedSteps.push({
        stepId: `step-intake-${task.task_id}`,
        state: "INTAKE",
        title: "Task Intake & Classification",
        description: `Request: "${task.user_request}"`,
        status: "passed",
        timestamp: nowTime,
      })

      if (task.plan && Array.isArray(task.plan)) {
        mappedSteps.push({
          stepId: `step-plan-${task.task_id}`,
          state: "PLAN",
          title: "Execution Plan Formulated",
          description: task.plan.join(" → "),
          status: "passed",
          timestamp: nowTime,
        })
      }

      if (task.tool_calls && Array.isArray(task.tool_calls)) {
        for (const [idx, tc] of task.tool_calls.entries()) {
          mappedSteps.push({
            stepId: `step-tool-${idx}-${task.task_id}`,
            state: "TOOL",
            title: `Executed Tool: ${tc.tool || "tool"}`,
            description: typeof tc.stdout === "string" ? tc.stdout : tc.ok ? "Completed successfully" : "Execution completed",
            status: tc.ok !== false ? "passed" : "failed",
            timestamp: nowTime,
          })
        }
      }

      if (task.current_state === "APPROVAL") {
        mappedSteps.push({
          stepId: `step-approval-${task.task_id}`,
          state: "APPROVAL",
          title: "Human Approval Gate Required",
          description: "Execution paused awaiting sign-off by inspection officer.",
          status: "pending",
          timestamp: nowTime,
        })
      } else if (task.current_state === "COMPLETE") {
        mappedSteps.push({
          stepId: `step-complete-${task.task_id}`,
          state: "COMPLETE",
          title: "Task Completed",
          description: task.approved_by ? `Approved by ${task.approved_by}` : "Execution finished and verified.",
          status: "passed",
          timestamp: nowTime,
        })
      } else if (task.current_state === "FAILED") {
        mappedSteps.push({
          stepId: `step-failed-${task.task_id}`,
          state: "FAILED",
          title: "Task Failed",
          description: task.errors ? JSON.stringify(task.errors) : "Task execution encountered errors.",
          status: "failed",
          timestamp: nowTime,
        })
      }

      const citations = mapChunksToCitations(task.retrieved_chunks, task.task_id)

      const artifacts = mapManifests(task.artifacts || [], nowTime)

      const loadedTaskState: TaskState = {
        taskId: task.task_id,
        userPrompt: task.user_request,
        // `task_type` is null until the orchestrator classifies the task, so null is
        // the correct value here. It previously fell back to the invented string
        // "general" through an `as any` cast -- a fourth task type that G7 does not
        // define, presented as though the backend had reported it.
        taskType: asTaskType(task.task_type),
        currentState: task.current_state,
        routing: routingFromTaskRecord(task),
        steps: mappedSteps,
        citations,
        artifacts,
        pidGraph: task.pid_graph as any,
        requiresApproval: task.current_state === "APPROVAL",
        approvalStatus: task.approved_by ? "approved" : undefined,
        finalResult: task.final_result
          ? (typeof task.final_result === "string" ? task.final_result : JSON.stringify(task.final_result, null, 2))
          : null,
        createdAt: nowTime,
        updatedAt: nowTime,
      }

      setActiveTask(loadedTaskState)
      if (artifacts.length > 0) setActiveTab("artifacts")
      else if (citations.length > 0) setActiveTab("sources")
      else if (task.pid_graph) setActiveTab("pid")
    } catch (err) {
      console.error("Failed to load task:", err)
    }
  }, [])

  const handleApprove = useCallback(
    async (approver: string, note?: string) => {
      if (!activeTask?.taskId) return
      const current = activeTask

      let res: { task_id: string; current_state: string; approved_by: string }
      try {
        res = await apiClient.approveTask(current.taskId, approver, "approve", note)
      } catch (err) {
        // The previous version caught the error, logged a warning, and then set the task
        // to COMPLETE with a step reading "approved ... Deliverables signed and archived".
        // A 409 CONFLICT (task not in APPROVAL) therefore displayed as a successful
        // sign-off. A decision is only recorded when the backend accepts it.
        setActiveTask((prev) =>
          prev
            ? {
                ...prev,
                approvalError: describeError(err),
              }
            : prev
        )
        return
      }

      const updatedTask: TaskState = {
        ...current,
        // State and approver come from the backend response, not from a local guess.
        currentState: (res.current_state as TaskState["currentState"]) ?? "COMPLETE",
        approvalStatus: "approved",
        requiresApproval: false,
        approvalError: undefined,
        approvedBy: res.approved_by,
        steps: [
          ...current.steps,
          {
            stepId: `step-approval-${Date.now()}`,
            state: "COMPLETE",
            title: "Human Sign-off Confirmed",
            description: `${res.approved_by || approver} approved via the approval gate.${
              note ? ` Note: ${note}` : ""
            }`,
            durationMs: 40,
            status: "passed",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ],
      }

      setActiveTask(updatedTask)
      await refreshRecentTasks()
    },
    [activeTask, refreshRecentTasks]
  )

  const handleReject = useCallback(
    async (approver: string, note?: string) => {
      if (!activeTask?.taskId) return
      const current = activeTask

      let res: { task_id: string; current_state: string; approved_by: string }
      try {
        res = await apiClient.approveTask(current.taskId, approver, "reject", note)
      } catch (err) {
        setActiveTask((prev) =>
          prev
            ? {
                ...prev,
                approvalError: describeError(err),
              }
            : prev
        )
        return
      }

      const updatedTask: TaskState = {
        ...current,
        currentState: (res.current_state as TaskState["currentState"]) ?? "FAILED",
        approvalStatus: "rejected",
        requiresApproval: false,
        approvalError: undefined,
        approvedBy: res.approved_by,
        steps: [
          ...current.steps,
          {
            stepId: `step-rejected-${Date.now()}`,
            state: "FAILED",
            title: "Human Review: Recommendation Rejected",
            description: `${res.approved_by || approver} rejected via the approval gate.${
              note ? ` Note: ${note}` : ""
            }`,
            durationMs: 30,
            status: "failed",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ],
      }

      setActiveTask(updatedTask)
      await refreshRecentTasks()
    },
    [activeTask, refreshRecentTasks]
  )

  const handleModify = useCallback(async () => {
    if (!activeTask) return
    // No backend route accepts a "modify and re-run" instruction: the approval
    // endpoint (app/api/tasks.py) accepts only decision=approve|reject. The previous
    // implementation set currentState to REPAIR locally and appended a step claiming
    // the agent was "re-evaluating tolerance parameters with modified safety margin",
    // which nothing performed. Report the absence instead of simulating the repair.
    setActiveTask((prev) =>
      prev
        ? {
            ...prev,
            approvalError:
              "The backend exposes no endpoint to request a re-analysis. " +
              "Use Reject with a note, then start a new task with the corrected parameters.",
          }
        : prev
    )
  }, [activeTask])

  /**
   * Re-read sovereignty telemetry from the backend.
   *
   * This REPLACED `triggerSimulatedEgress`, which fabricated a blocked packet to
   * "api.anthropic.com:443 (160.79.104.10)" with a made-up protocol, process name and
   * netfilter reason, and incremented the denied-attempt counter — all from a local
   * state mutation, with no network call and no backend involvement. The header then
   * displayed a rising denial count that nothing had produced.
   *
   * There is deliberately no simulated variant. The real guard is
   * `app/net/egress_guard.py`, a host-level socket patch installed at startup
   * (`app/main.py:58`) that increments `denied_connections` and emits `EGRESS_DENIED`
   * when a connection is actually refused. No HTTP endpoint exposes a "try an egress"
   * action, so the UI can only display what the backend has genuinely counted.
   * See Frontend-fix.md item 1.9.
   */
  const refreshSovereignty = useCallback(async () => {
    await checkBackendState()
  }, [checkBackendState])

  /**
   * Apply one stream event to the active task.
   *
   * Shared by the two ways events arrive (Frontend-fix.md item 2.1):
   *
   *   * `submitMessage` -> `POST /api/chat` streaming from event 1
   *   * `resumeActiveTask` -> `GET /api/tasks/{id}/stream` replaying from the cursor
   *
   * They must not be two reducers. When they were, a task resumed after a page
   * refresh rendered its replayed events differently from a task watched live, and
   * the divergence was only visible in the one case a user is least likely to
   * reproduce deliberately. Extracted verbatim; the body is unchanged.
   */
  const applyStreamEvent = useCallback((event: ChatStreamEvent) => {
    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    const eventType = event.type
    const data = (event.data || {}) as Record<string, any>

    // Advance the resume cursor for every event, on either path, so the two cannot
    // drift. Only frames that carry an `id:` move it; a frame without one has no
    // position to record and must not be assumed to be the newest.
    if (event.id) recordEventId(event.id)

    setActiveTask((prev) => {
      // No task to update. The old inline version returned the `newTask` captured
      // from `submitMessage` here, which does not exist on the resume path.
      if (!prev) return prev
      // `const`, not `let`: every branch below mutates properties of this object
      // rather than rebinding it, so the binding is never reassigned.
      const updated = { ...prev }

      if (eventType === "state_changed") {
        const nextState = (data.state || "INTAKE") as AgentState
        updated.currentState = nextState
        if (data.task_type) {
          updated.taskType = asTaskType(data.task_type)
        }
      } else if (eventType === "model_selected") {
        updated.routing = routingFromModelSelected(data)
      } else if (eventType === "plan") {
        const stepsList = data.steps || []
        const newStep: AgentStep = {
          stepId: `step-plan-${Date.now()}`,
          state: "PLAN",
          title: "Execution Plan Formulated",
          description: Array.isArray(stepsList) ? stepsList.join(" → ") : String(stepsList),
          status: "passed",
          timestamp: timeStr,
        }
        updated.steps = [...updated.steps, newStep]
      } else if (eventType === "tool_proposed") {
        const newStep: AgentStep = {
          stepId: `step-tool-${Date.now()}`,
          state: "TOOL",
          title: `Executing Tool: ${data.tool || "tool"}`,
          description: data.args ? JSON.stringify(data.args) : "Invoking tool",
          status: "running",
          timestamp: timeStr,
        }
        updated.steps = [...updated.steps, newStep]
      } else if (eventType === "tool_result") {
        const toolName = data.tool || "Tool"
        const isOk = data.ok !== false
        const newStep: AgentStep = {
          stepId: `step-toolres-${Date.now()}`,
          state: "TOOL",
          title: `Tool Output: ${toolName}`,
          description: data.stdout || data.error || (isOk ? "Completed successfully" : "Execution failed"),
          status: isOk ? "passed" : "failed",
          timestamp: timeStr,
        }
        updated.steps = [...updated.steps, newStep]
      } else if (eventType === "retrieval") {
        const citations = mapChunksToCitations(data.chunks, String(updated.taskId ?? "task"))
        updated.citations = citations
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-ret-${Date.now()}`,
            state: "RETRIEVE",
            title: `Retrieved ${citations.length} SOP Clauses`,
            description: `Matched relevant guidelines from Qdrant vector database.`,
            status: "passed",
            timestamp: timeStr,
          },
        ]
      } else if (eventType === "verification") {
        const isPassed = data.status === "passed"
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-ver-${Date.now()}`,
            state: "VERIFY",
            title: `Verification: ${isPassed ? "PASSED" : "FAILED"}`,
            description: data.details || "Validated formulas and assertions.",
            status: isPassed ? "passed" : "failed",
            timestamp: timeStr,
          },
        ]
      } else if (eventType === "repair") {
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-rep-${Date.now()}`,
            state: "REPAIR",
            title: `Auto-Repair Loop: Attempt #${data.attempt || 1}`,
            description: data.reason || "Self-correcting parameters and re-verifying.",
            status: "repaired",
            timestamp: timeStr,
          },
        ]
      } else if (eventType === "artifact_created") {
        if (updated.taskId) {
          // The event itself carries only `{artifact_id, artifact_type}`, so refetch the
          // task for the real manifests. This used to inline a second, slightly
          // different copy of the mapping below -- which is how the "Validated
          // deliverable" size string ended up in two places and both had to be fixed.
          // It now calls `mapManifests`, so there is one implementation.
          apiClient.getTask(updated.taskId).then((taskData) => {
            if (taskData.artifacts) {
              setActiveTask((t) =>
                t
                  ? { ...t, artifacts: mapManifests(taskData.artifacts ?? [], timeStr) }
                  : t
              )
            }
          })
        }
      } else if (eventType === "approval_requested") {
        updated.currentState = "APPROVAL"
        updated.requiresApproval = true
        // The `approval_requested` event carries only {artifact_ids, summary} (G9).
        // Measurements, thresholds, standard references and compliance verdicts are
        // NOT in the payload. They are left unset rather than synthesised — a
        // fabricated safety-critical number is the worst thing this UI could show.
        // See Frontend-fix.md item 1.4.
        const summary = typeof data.summary === "string" ? data.summary : undefined
        const artifactIds = Array.isArray(data.artifact_ids)
          ? (data.artifact_ids as unknown[]).map(String).filter(Boolean)
          : []
        updated.approvalData = {
          ...(summary ? { recommendation: summary } : {}),
          ...(artifactIds.length ? { deliverablesPending: artifactIds } : {}),
        }
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-app-req-${Date.now()}`,
            state: "APPROVAL",
            title: "Safety Gate Triggered: Awaiting Human Sign-off",
            description: data.summary || "Halting execution for human review.",
            status: "pending",
            timestamp: timeStr,
          },
        ]
      } else if (eventType === "completed") {
        updated.currentState = "COMPLETE"
        if (data.final_result) {
          updated.finalResult = typeof data.final_result === "string"
            ? data.final_result
            : JSON.stringify(data.final_result, null, 2)
        }
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-complete-${Date.now()}`,
            state: "COMPLETE",
            title: "Task Execution Completed Successfully",
            description: "All steps, verifications, and deliverables finalized.",
            status: "passed",
            timestamp: timeStr,
          },
        ]
      } else if (eventType === "failed") {
        updated.currentState = "FAILED"
        const errMsg = data.error?.message || "Task execution failed"
        updated.steps = [
          ...updated.steps,
          {
            stepId: `step-fail-${Date.now()}`,
            state: "FAILED",
            title: "Task Execution Failed",
            description: errMsg,
            status: "failed",
            timestamp: timeStr,
          },
        ]
      }

      return updated
    })
  }, [recordEventId])

  /**
   * Reattach to a task's event stream (Frontend-fix.md item 2.1).
   *
   * There are two situations and they need different strategies, because the
   * backend's snapshot and its event log overlap:
   *
   * **The in-memory task survived** — the SSE connection dropped but the page did
   * not. Resume from the cursor. `GET /api/tasks/{id}/stream` replays only ids
   * greater than `Last-Event-Id`, so the steps already on screen stay untouched.
   * This is the case the header exists for.
   *
   * **The in-memory task is gone** — the page was reloaded. There is nothing to
   * resume *into*, and the cursor points at a mid-run position whose earlier events
   * no longer exist in the client. So the whole log is replayed from id 0, which
   * rebuilds the task exactly as a live run built it.
   *
   * `loadTask` is deliberately NOT used to seed the rebuild. It maps steps from the
   * aggregate columns — `task.plan` and `task.tool_calls` — under its own step ids
   * (`step-plan-${task_id}`, `step-tool-${idx}-${task_id}`), whereas replayed events
   * use `step-plan-${Date.now()}`. Seeding from the snapshot and then replaying
   * therefore appends a *second* copy of every plan and tool step. That duplication
   * is the specific bug this two-strategy split avoids.
   *
   * Artifacts are the one thing replay cannot rebuild: the `artifact_created` event
   * carries only `{artifact_id, artifact_type}` (G9) — no path, no verification
   * status — so those come from the snapshot, merged after the replay.
   *
   * Returns true if a task was resumed, so callers can report accurately.
   */
  const resumeActiveTask = useCallback(async (): Promise<boolean> => {
    const cursor = readCursor()
    if (!cursor) return false

    const stateSurvived = activeTask?.taskId === cursor.taskId
    // Re-arm the in-memory refs so events arriving on the resumed stream keep the
    // cursor moving. Without this a resumed stream would record nothing.
    writeCursor(cursor.taskId, cursor.lastEventId)

    const controller = new AbortController()
    resumeAbortRef.current = controller

    try {
      if (stateSurvived) {
        if (!RESUMABLE_STATES.has(activeTask.currentState)) {
          // Already finished, failed, or awaiting sign-off. Nothing left to stream,
          // and opening one would sit idle on a task that will not move by itself.
          resumeAbortRef.current = null
          return false
        }
        setIsExecuting(true)
        await apiClient.resumeStream(cursor.taskId, cursor.lastEventId ?? undefined, {
          onEvent: applyStreamEvent,
          signal: controller.signal,
        })
        return true
      }

      // State was lost. The snapshot decides both whether to stream and what the
      // artifacts are.
      const snapshot = await apiClient.getTask(cursor.taskId)

      if (!RESUMABLE_STATES.has(snapshot.current_state)) {
        // Terminal, or waiting for a human. The summary mapping is accurate for a
        // settled task, so use it instead of replaying events.
        resumeAbortRef.current = null
        await loadTask(cursor.taskId)
        return true
      }

      setIsExecuting(true)
      await apiClient.resumeStream(cursor.taskId, undefined, {
        onEvent: applyStreamEvent,
        signal: controller.signal,
      })

      // Merge artifact manifests, which the event stream cannot carry.
      const nowTime = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
      setActiveTask((prev) =>
        prev && prev.taskId === cursor.taskId
          ? {
              ...prev,
              artifacts: mapManifests(snapshot.artifacts || [], nowTime),
              approvalStatus: snapshot.approved_by
                ? "approved"
                : prev.approvalStatus,
              approvedBy: snapshot.approved_by ?? prev.approvedBy,
            }
          : prev
      )
      return true
    } catch (err) {
      if (controller.signal.aborted) return false
      // The backend may be unreachable, or the task may have been removed. Either
      // way this is a transport problem, not a task outcome: the state is left alone
      // and the reason is surfaced as such.
      setActiveTask((prev) =>
        prev
          ? {
              ...prev,
              streamError: `Could not resume the event stream: ${describeError(err)}`,
            }
          : prev
      )
      return false
    } finally {
      resumeAbortRef.current = null
      setIsExecuting(false)
    }
  }, [activeTask, applyStreamEvent, readCursor, writeCursor, loadTask])

  /**
   * Submit a user message and stream the resulting task.
   *
   * On a transport failure with a live task id this hands off to
   * `resumeActiveTask` instead of reporting a task failure. See the comment there.
   */
  const submitMessage = useCallback(
    async (message: string, attachedFiles?: File[]) => {
      setIsExecuting(true)
      const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      const tempTaskId = `task-${Date.now()}`

      // Optimistic placeholder only. It previously named the locally selected model,
      // which asserts a backend decision the orchestrator has not made yet -- and in
      // stub mode the active model cannot even be set (item 2.4: 501). Replaced as soon
      // as a `model_selected` event arrives. See `lib/routing.ts`.
      const initialRouting: RoutingReceipt = pendingRouting()

      const newTask: TaskState = {
        taskId: tempTaskId,
        userPrompt: message,
        // No backend classification yet. Was the literal "general", a task type G7 does
        // not define; null is what the `tasks` column actually holds at INTAKE.
        taskType: null,
        currentState: "INTAKE",
        routing: initialRouting,
        steps: [
          {
            stepId: `step-intake-${Date.now()}`,
            state: "INTAKE",
            title: "Task Intake & Classification",
            description: `Received prompt: "${message.slice(0, 70)}${message.length > 70 ? "..." : ""}"`,
            status: "passed",
            timestamp: nowTime,
          },
        ],
        citations: [],
        artifacts: [],
        requiresApproval: false,
        createdAt: nowTime,
        updatedAt: nowTime,
      }

      setActiveTask(newTask)

      try {
        let fileIds: string[] = []
        if (attachedFiles && attachedFiles.length > 0) {
          const uploadRes = await apiClient.uploadFiles(attachedFiles)
          fileIds = uploadRes.files.map((f) => f.file_id)
        }

        await apiClient.chatStream(message, {
          fileIds,
          onTaskId: (id) => {
            setActiveTask((prev) => (prev ? { ...prev, taskId: id } : prev))
            // Arm the cursor with the real id. Done here rather than at task creation
            // because `newTask.taskId` is the optimistic `task-${Date.now()}` label,
            // which the backend does not know and cannot replay.
            writeCursor(id, null)
          },
          onEvent: applyStreamEvent,
        })
      } catch (err: any) {
        console.error("Task execution error:", err)
        // Did the backend create a task before this error? `onTaskId` fires only after
        // the response headers arrive, and it arms the cursor, so a live cursor means
        // the task exists and is running on the backend no matter what the client saw.
        if (cursorTaskIdRef.current) {
          // Transport problem, not a task outcome. G11 requires that a client
          // disconnect not cancel the task, so the state must not be relabelled
          // FAILED. Reattach from the cursor instead and report only a resume failure.
          setActiveTask((prev) =>
            prev ? { ...prev, streamError: `Connection lost: ${describeError(err)}` } : prev
          )
          await resumeActiveTask()
        } else {
          // No task id: the request never got that far (upload failed, 429, 502).
          // Nothing is running, so there is no task to misreport.
          setActiveTask((prev) => {
            if (!prev) return newTask
            return {
              ...prev,
              currentState: "FAILED",
              streamError: err.message || "Failed to communicate with backend.",
              steps: [
                ...prev.steps,
                {
                  stepId: `step-err-${Date.now()}`,
                  state: "FAILED",
                  title: "Request Failed",
                  description: err.message || "Failed to communicate with backend.",
                  status: "failed",
                  timestamp: new Date().toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  }),
                },
              ],
            }
          })
        }
      } finally {
        setIsExecuting(false)
        await refreshRecentTasks()
      }
    },
    [refreshRecentTasks, applyStreamEvent, writeCursor, resumeActiveTask]
  )

  /**
   * On mount, pick an interrupted task back up (Frontend-fix.md item 2.1).
   *
   * A reload during a task used to leave the UI showing whatever the previous render
   * had, which after a reload is nothing: the task kept running on the backend and
   * its events were never read again. The cursor in `sessionStorage` is what makes the
   * task recoverable, and `resumeActiveTask` decides between replaying from the cursor
   * and replaying the whole log.
   *
   * `sessionStorage` rather than `localStorage` on purpose: it is scoped to the tab
   * and survives a refresh, which is exactly the case worth covering. A task should
   * not silently reappear hours later in a new session, and the audit log is
   * append-only, so quietly resurrecting an old task would misrepresent the record.
   *
   * The ref guard is required, not decorative: React StrictMode invokes mount effects
   * twice in development, and without it two resume streams would attach to the same
   * task and every replayed event would render twice.
   */
  useEffect(() => {
    if (resumeAttemptedRef.current) return
    resumeAttemptedRef.current = true
    void resumeActiveTask()
    // Intentionally mount-only. `resumeActiveTask` changes identity on every task
    // update, and depending on it here would re-run the effect and re-resume forever.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Abort any in-flight resume if the provider unmounts, so a closed tab does not
  // leave a reader running against a task nobody is watching.
  useEffect(() => {
    return () => {
      resumeAbortRef.current?.abort()
    }
  }, [])


  return (
    <WorkbenchContext.Provider
      value={{
        activeTask,
        recentTasks,
        sovereignty,
        selectedNode,
        setSelectedNode,
        activeTab,
        setActiveTab,
        isContextPanelOpen,
        setIsContextPanelOpen,
        isExpandedView,
        setIsExpandedView,
        isBackendConnected,
        isExecuting,
        handleApprove,
        handleReject,
        handleModify,
        refreshSovereignty,
        submitMessage,
        loadTask,
        refreshRecentTasks,
        resetTask,
        activeModelId,
        setActiveModelId,
      }}
    >
      {children}
    </WorkbenchContext.Provider>
  )
}

export function useWorkbench() {
  const context = useContext(WorkbenchContext)
  if (!context) {
    throw new Error("useWorkbench must be used within a WorkbenchProvider")
  }
  return context
}
