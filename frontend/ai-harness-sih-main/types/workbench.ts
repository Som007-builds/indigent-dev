export type TaskType = 'inspection' | 'coding' | 'pid_analysis' | 'general' | 'sovereignty_proof'

export type AgentState = 
  | 'INTAKE' 
  | 'CLASSIFY' 
  | 'PLAN' 
  | 'RETRIEVE' 
  | 'TOOL' 
  | 'VERIFY' 
  | 'REPAIR' 
  | 'ARTIFACT' 
  | 'ARTIFACT_VALIDATE'
  | 'APPROVAL' 
  | 'COMPLETE' 
  | 'FAILED'

export type ModelRole = 'reasoning' | 'coding' | 'vision' | 'embedding' | 'general'

export interface RoutingReceipt {
  modelId: string
  modelName: string
  role: ModelRole
  reason: string
  /**
   * Deliberately optional. The `model_selected` event (G9) carries
   * `{model_id, model_name, provider}` and no residency flag, so this was previously
   * hardcoded `true` at all three construction sites — asserting that a model was
   * resident in VRAM on the backend's behalf. Residency is real data, but it lives on
   * `GET /api/models` (`resident_models` / `models[].resident`), not on a task event.
   * Absent means "not reported", which is not the same as false. See `lib/routing.ts`.
   */
  isResident?: boolean
  contextLength?: string
  vramUsageGb?: number
}

export interface AgentStep {
  stepId: string
  state: AgentState
  title: string
  description?: string
  tool?: string
  toolInput?: Record<string, unknown> | string
  toolOutput?: Record<string, unknown> | string
  durationMs?: number
  status: 'pending' | 'running' | 'passed' | 'failed' | 'repaired'
  timestamp: string
}

export interface SOPCitation {
  id: string
  /** Chunk or document id as returned by the backend. Never an invented SOP number. */
  source: string
  title: string
  /** Optional: the backend only returns `section` when the chunk actually carries one. */
  section?: string
  page?: number
  snippet: string
  /** Optional: shown only when the backend supplies a score. */
  confidence?: number
  matchedClause?: string
  toleranceRequired?: string
}

export interface ArtifactDeliverable {
  id: string
  filename: string
  fileType: 'docx' | 'xlsx' | 'pptx' | 'py' | 'json' | 'pdf'
  fileSizeFormatted: string
  downloadUrl: string
  validationStatus: 'validated' | 'warning' | 'error'
  validationMessage?: string
  summary: string
  generatedAt: string
}

export interface PIDNode {
  id: string
  tag: string           // e.g. "FCV-101"
  symbolType: 'control_valve' | 'centrifugal_pump' | 'distillation_column' | 'heat_exchanger' | 'pressure_transmitter' | 'storage_tank' | 'check_valve' | 'reactor' | 'knockout_drum' | 'compressor' | 'furnace' | 'accumulator' | 'instrument' | 'vessel' | string
  label: string
  bbox: [number, number, number, number] // [x, y, width, height] in percentage 0-100
  confidence: number
  lineAssociation?: string
  status?: 'nominal' | 'alert' | 'unverified'
  description?: string
}

export interface PIDEdge {
  id: string
  fromNodeId: string
  toNodeId: string
  lineType: 'process_pipe' | 'instrument_line' | 'electrical_signal' | 'steam_line'
  lineTag: string
  flowDirection: 'forward' | 'bidirectional'
  confidence: number
}

export interface PIDGraph {
  drawingId: string
  drawingTitle: string
  // Optional: the backend PIDGraph carries no standard/category field, so these
  // stay unset for analysed uploads rather than being filled with a plausible value.
  standard?: string     // e.g. "ISA-5.1"
  category?: string
  description?: string
  nodes: PIDNode[]
  edges: PIDEdge[]
  // Servable URL of the rendered overlay. Omitted when no overlay artifact exists.
  overlayImageUrl?: string
  flowNarrative?: string
  equipmentCount?: {
    valves: number
    pumps: number
    vessels: number
    instruments: number
  }
}

export interface SovereigntyMetrics {
  /**
   * False until `/api/monitoring/sovereignty` has actually answered.
   *
   * Every other field in this interface is meaningless while this is false: the
   * counters are "not reported", not "zero", and `isAirGapped` is "unknown", not
   * "true". The UI must render a distinct unknown state rather than defaulting to
   * a reassuring value — see Frontend-fix.md item 1.7.
   */
  statusKnown: boolean
  isAirGapped: boolean
  internetBlocked: boolean
  externalApiCalls: number
  externalDnsQueries: number
  externalConnections: number
  localRequests: number
  statusText: string
  activeFirewallRules: number
  deniedConnectionAttempts?: number
  externalBytesOut?: number
  externalBytesIn?: number
  provider?: string
  inferenceMode?: 'local' | 'groq'
  networkPolicy?: string
  /**
   * Set when `X-Inference-Mode` and `/api/monitoring/sovereignty` disagree.
   * The backend asserts three-way agreement in
   * `tests/integration/test_inference_mode_reporting.py`, so a conflict means the UI
   * is talking to an inconsistent backend. Surfaced rather than silently resolved.
   */
  modeConflict?: string
  lastBlockedPacket?: {
    timestamp: string
    destination: string
    protocol: string
    process: string
    reason: string
  }
}

export interface ApprovalData {
  /** Free-text summary from the backend `approval_requested` event. */
  recommendation?: string
  /** Artifact ids awaiting sign-off (the event sends ids, not filenames). */
  deliverablesPending?: string[]
  /**
   * The backend `approval_requested` event carries only {artifact_ids, summary}.
   * Everything below stays unset unless a producer actually supplies it. These are
   * never defaulted to a plausible engineering value — see Frontend-fix.md item 1.4.
   */
  rationale?: string
  standardRef?: string
  measuredValue?: string
  thresholdValue?: string
  complianceStatus?: 'REJECT' | 'APPROVE' | 'CONDITIONAL'
  reviewerRoleRequired?: string
}

export interface TaskState {
  taskId: string
  scenarioKey?: 'inspection_report' | 'sandbox_repair' | 'sovereignty_proof' | 'pid_analysis'
  scenarioTitle?: string
  userPrompt: string
  taskType: TaskType
  currentState: AgentState
  routing: RoutingReceipt
  steps: AgentStep[]
  citations: SOPCitation[]
  artifacts: ArtifactDeliverable[]
  pidGraph?: PIDGraph | null
  approvalData?: ApprovalData | null
  requiresApproval: boolean
  approvalStatus?: 'pending' | 'approved' | 'rejected'
  /** Approver string as recorded by the backend on a successful decision. */
  approvedBy?: string
  /**
   * Set when an approval/reject/modify action did NOT succeed. The task state is left
   * untouched in that case, so the UI must surface this rather than implying the
   * decision was recorded. See Frontend-fix.md item 1.8.
   */
  approvalError?: string
  /**
   * Set when the event stream could not be read or resumed — a dropped connection, an
   * unreachable backend, a task that no longer exists.
   *
   * Distinct from a task failure on purpose. Per G11 a client disconnect must not
   * cancel the task: the backend keeps running it, so `currentState` is left
   * untouched. The previous implementation set `currentState = "FAILED"` for *any*
   * error here, which asserted the task had failed when it had not, and destroyed
   * the task's resumability at the same moment it was most needed.
   * See Frontend-fix.md item 2.1.
   */
  streamError?: string
  finalResult?: string | null
  createdAt: string
  updatedAt: string
}

export interface ModelRegistryItem {
  id: string
  name: string
  role: ModelRole
  /**
   * Optional: the backend /api/models payload is
   * {id, type, tasks, provider, model_name, available, resident, memory_estimate_mb}.
   * It carries none of the descriptive fields below, so they stay unset rather than
   * being defaulted to plausible cloud values. See Frontend-fix.md item 1.6.
   */
  paramCount?: string
  /** Reported by the backend as `provider` (e.g. "ollama"). */
  provider?: string
  tasks: string[]
  contextLength?: number | string
  quantization?: string
  /** Derived from the backend's memory_estimate_mb. */
  vramGb?: number
  /** Backend field is `resident` (not `isResident`). */
  isResident: boolean
  priority: number
  architecture?: string
  speedTokSec?: number | string
  firstTokenMs?: number
  engineBackend?: string
  filePath?: string
  checksumSha256?: string
  layersOffloaded?: number
  totalLayers?: number
  status?: 'resident' | 'standby' | 'available' | 'loading'
  authorOrOrg?: string
  isCustom?: boolean
}

// ==========================================
// Exact Backend API Contracts & Wire Schemas
// ==========================================

export interface BackendArtifactItem {
  artifact_id: string
  task_id: string
  artifact_type: 'docx' | 'xlsx' | 'graph_json' | 'code_package' | 'pid_overlay'
  path: string
  created_at: string
  artifact_hash: string
  source_evidence_ids: string[]
  verification_status: 'pending' | 'passed' | 'failed'
  metadata: Record<string, unknown>
  download_url?: string
}

export interface BackendTaskResponse {
  task_id: string
  user_request: string
  task_type: string | null
  inference_mode: 'local' | 'groq'
  plan: string[] | null
  current_state: AgentState
  model_used: string | null
  tool_calls: Array<Record<string, unknown>> | null
  retrieved_chunks: Array<Record<string, unknown>> | null
  pid_graph: Record<string, unknown> | null
  errors: Array<Record<string, unknown>> | null
  final_result: Record<string, unknown> | null
  approved_by: string | null
  approval_note: string | null
  verification_status: string
  artifacts: BackendArtifactItem[]
  created_at?: string
}

/**
 * One row of the `audit_log` table, as returned by `GET /api/tasks/{id}/timeline`
 * and `GET /api/tasks/timeline/all`.
 *
 * This interface previously declared `seq`, `event_type` and `actor` — **none of
 * which are columns of `audit_log`** (`app/core/schema.sql:8-9`, mirrored in G10).
 * `seq` belongs to `task_events`, a different table. Because the fields were typed as
 * present, the UI read them, got `undefined`, and substituted fabricated stand-ins
 * ("Orchestrator", "State Transition", a row index). The real columns are below;
 * required-ness follows the NOT NULL constraints.
 */
export interface BackendAuditItem {
  id: number
  /** Nullable in the schema — the all-tasks timeline spans many tasks. */
  task_id?: string | null
  ts: string
  /** NOT NULL in the schema. Records which inference mode produced the row. */
  inference_mode: string
  category: string
  component: string
  action: string
  /** Written as ok | error | denied, defaulting to info (app/core/audit.py:38). */
  status: string
  details?: Record<string, unknown>
}

export interface BackendTimelineResponse {
  /**
   * Present on `GET /api/tasks/{id}/timeline` but **absent** on
   * `GET /api/tasks/timeline/all`, which returns only `{entries: [...]}`.
   * Declared required, so the all-tasks shape did not typecheck honestly.
   */
  task_id?: string
  entries: BackendAuditItem[]
}

/**
 * One row of the `files` table as returned by `GET /api/files` and
 * `POST /api/files/upload` (`app/api/files.py`).
 *
 * `created_at` and `task_id` are only present on the list response, and
 * `download_url` on both — the Documents page previously built its download link from
 * the *name* because this interface had no `download_url`, so every download hit a
 * route that did not exist (Frontend-fix.md item 2.2).
 */
export interface BackendUploadedFile {
  file_id: string
  name: string
  size: number
  sha256: string
  mime: string
  kind: 'upload' | 'knowledge' | 'pid'
  /** Present on `GET /api/files` only. */
  created_at?: string
  /** Nullable in the schema; present on `GET /api/files` only. */
  task_id?: string | null
  /** Added by `GET /api/files/{file_id}`. Keyed by `file_id`, never by name. */
  download_url?: string
}

export interface BackendFileUploadResponse {
  files: BackendUploadedFile[]
}

export interface BackendKnowledgeUploadFile {
  file_id: string
  name: string
  size: number
  sha256: string
  mime: string
  ingest_status: 'pending' | 'ingesting' | 'ready' | 'failed'
}

export interface BackendKnowledgeUploadResponse {
  files: BackendKnowledgeUploadFile[]
}

export interface BackendKnowledgeStatusResponse {
  file_id: string
  name: string
  ingest_status: 'pending' | 'ingesting' | 'ready' | 'failed'
  ingest_error: string | null
}

export interface BackendSovereigntyResponse {
  inference_mode: 'local' | 'groq'
  status: string
  provider: string
  network_policy: string
  internet_access: string
  sandbox_network: string
  external_api_calls: number
  external_connections: number
  external_bytes_out: number
  external_bytes_in: number
  denied_connection_attempts: number
  since: string
}

export interface BackendModelsResponse {
  active_inference_mode: string
  hardware_profile: string
  active_model_id?: string
  models: Array<Record<string, unknown>>
  resident_models: Array<string>
  resources: {
    vram_mb_free: number
    ram_mb_free: number
    disk_mb_free: number
    max_concurrency: number
  }
}

export interface BackendPIDAnalyzeResponse {
  task_id: string
  graph: {
    nodes: Array<Record<string, unknown>>
    edges: Array<Record<string, unknown>>
    /**
     * Server-side filesystem path (e.g. data/pid/{file_id}/overlay.png).
     * NOT servable as-is — resolve the overlay through artifact_ids instead.
     */
    overlay_image_path: string
    narrative: string
    confidence_summary: Record<string, unknown>
    /** Set by app/api/pid.py:38. Equivalent to artifact_ids[1]. */
    overlay_artifact_id?: string
  }
  /** [graph_json_artifact_id, overlay_artifact_id] — see app/api/pid.py. */
  artifact_ids: string[]
}

export interface BackendReadyzResponse {
  sqlite: 'ok' | 'fail'
  docker: 'ok' | 'fail'
  sandbox_image: 'ok' | 'fail'
  qdrant: 'ok' | 'fail'
  ollama: 'ok' | 'fail'
}
