G — GLOBAL CONTEXT  
G1 Product

Air-gapped AI assistant for refineries/PSUs/defence manufacturing. Data (P&IDs, financials, vendor terms, designs) must never leave the machine. Runs on ONE local machine: plan → use tools → read documents/images → write real deliverables (DOCX/XLSX/code), with "nothing leaves this device" proven live in a Sovereignty Monitor. Stack: React frontend → FastAPI → agent orchestrator → policy layer → tools/sandbox; Ollama (local models), Qdrant (vectors), SQLite (state+audit), Docker (sandbox). Groq API exists ONLY as an opt-in dev/test inference path.

G2 Ownership boundary (never cross)
You (Soham) own mechanisms: API gateway, request/response schemas, SQLite persistence, SSE, files/workspaces, artifact storage/lifecycle, audit persistence, tool execution plumbing, Docker sandbox, knowledge/P&ID API plumbing, models/sovereignty API exposure, config/compose, logging, health, infra tests, frontend contract.
Joy owns intelligence: app/providers/, app/agent/ (orchestrator, router, resource manager, model registry), app/policy/ (policy validation, allow-lists), app/rag/, app/artifact_validation/, P&ID ML internals. Do not create or edit files in these dirs. You code against the interfaces in G8 and use stubs in app/stubs/.
Joint: end-to-end integration, security tests, demo reliability.
G3 Security invariants (violating any = bug)
LLM output never authorizes an action; every tool call needs a PolicyDecision(allowed=True) from Joy's validator before your runtime executes it.
Every filesystem path derived from model/user input goes through safe_join() (Step 4).
Sandbox: --network=none always (local AND groq mode). If Docker is unavailable → fail loudly (SANDBOX_UNAVAILABLE). Never fall back to host subprocess.
No Groq fallback, no mode switching. INFERENCE_MODE (local|groq) is read from config only, default local, never inferred.
Groq mode must never be shown as AIR-GAPPED.
Secrets (GROQ_API_KEY, anything matching key/token/secret/authorization) never logged, never in audit, never in API responses, never committed.
Unauthorized tools fail closed and are audited. Audit log is append-only.
Backend binds 127.0.0.1 only. Code and tests make zero external network calls.
Bounded everything: timeouts, sizes, output, concurrency.
G4 Stack, tooling, commands
Python 3.11+, FastAPI, uvicorn, pydantic v2 + pydantic-settings, aiosqlite, sse-starlette, python-multipart, docker (SDK), python-docx, openpyxl, Pillow, httpx, pytest, pytest-asyncio, ruff. Use latest stable; after Step 0 write resolved versions to requirements.lock (pip freeze).
Do NOT import ollama, groq, or any LLM SDK anywhere (Joy's providers/ only).
Commands: ruff check . · pytest -q · pytest -q -m "not docker" (no Docker) · uvicorn app.main:app --host 127.0.0.1 --port 8000.
Style: type hints, async I/O, small modules, no dead code, no TODOs left silently (log in docs/decisions.md).
Rule on gaps: if this doc is silent → use the DEFAULT in G7; if none → STOP and ask Soham. Record every deviation/choice in docs/decisions.md (1 line each).
Report format after each step (≤10 lines): files changed · tests run/passed · deviations · open questions.
G5 Repo layout
indigent/
  AGENTS.md  build.prd.md  pyproject.toml  requirements.lock  .env.example  .gitignore  docker-compose.yml
  app/
    main.py config.py errors.py logging_setup.py deps.py
    contracts/   models.py interfaces.py          # shared with Joy; frozen after Step 0
    stubs/       orchestrator.py policy.py rag.py pid.py ml_tools.py models_status.py artifact_validator.py
    api/         chat.py tasks.py files.py knowledge.py artifacts.py models.py monitoring.py pid.py health.py
    core/        db.py schema.sql repo.py events.py audit.py workspace.py files.py artifacts.py taskrunner.py
    runtime/     registry.py executor.py sandbox.py generators/{docx.py,xlsx.py}
    net/         egress_guard.py sovereignty.py
    policy/      allowlist.py   # JOY owns; you seed it from G7
    providers/ agent/ rag/ artifact_validation/     # JOY — do not touch
  sandbox/       Dockerfile selftest.py
  tests/         (mirror of app/)
  tools/         contract_check.py
  docs/          decisions.md contract-mismatches.md api-contract.md network-lockdown.md
  data/          (gitignored) db.sqlite  workspaces/  uploads/  pid/  logs/  qdrant/

Joy wiring switch: env JOY_MODULES=stub|real (default stub). deps.py picks stub or real EXPLICITLY (no try-import fallback).

G6 Config (app/config.py, pydantic-settings, .env.example has no secrets)
Var	Default	Notes
INFERENCE_MODE	local	must be local or groq, else refuse to start
LOCAL_HARDWARE_PROFILE	mac_silicon	mac_silicon | rtx_3050a_4gb
GROQ_API_KEY	(empty)	only read by Joy's provider; never logged
JOY_MODULES	stub	stub | real
API_HOST / API_PORT	127.0.0.1 / 8000	
CORS_ORIGINS	http://localhost:5173	comma list
DATA_DIR	./data	Mac+Docker Desktop: must be under a Docker-shared path (e.g. inside home dir)
OLLAMA_BASE_URL	http://localhost:11434	readiness only
QDRANT_URL	http://localhost:6333	readiness + passed to Joy
MAX_UPLOAD_MB / MAX_PID_IMAGE_MB	50 / 25	
MAX_MESSAGE_CHARS	20000	
MAX_ACTIVE_TASKS	2	more → 429
PER_TOOL_TIMEOUT_S	30	
MODEL_GENERATION_TIMEOUT_S	60	(Joy uses; exposed)
HARD_TASK_TIMEOUT_S	300	excludes time in APPROVAL
APPROVAL_TIMEOUT_S	86400	
PID_TIMEOUT_S	120	
SANDBOX_IMAGE	indigent-sandbox:1	
SANDBOX_MEM_MB / SANDBOX_CPUS / SANDBOX_PIDS	256 / 1 / 64	
SANDBOX_OUTPUT_LIMIT_KB	64	per stream
WORKSPACE_TTL_HOURS	24	scratch cleanup only; outputs+audit kept
LOG_LEVEL	INFO	
Startup: log mode + profile. If mode=groq log WARNING "EXTERNAL INFERENCE ACTIVE". Every HTTP response carries header X-Inference-Mode: <mode>.		
G7 Locked decisions & defaults
Backend runs on the HOST (not in Docker): Ollama needs host GPU/Metal; sandbox needs the Docker socket. Compose runs Qdrant only (Step 9).
No auth (IAM out of scope). approver is free text.
Ids: task_id = uuid4 str; file_id = uuid4 hex; artifact_id = uuid4 str. Timestamps: ISO-8601 UTC (2026-09-25T10:00:00Z).
Allowed upload types: .pdf .png .jpg .jpeg .tif .tiff .docx .xlsx .pptx .txt .md .csv .json. Verify magic bytes for pdf/images/office (zip). P&ID images: png/jpg/jpeg/tif/tiff only.
Task types: inspection, coding, pid_analysis (task_type set by orchestrator CLASSIFY; before that null).
ALLOWED_TOOLS (seed for app/policy/allowlist.py, Joy may edit later):
python
ALLOWED_TOOLS = {
 "inspection": {"read_file","ocr_document","search_knowledge_base","retrieve_section","create_docx","create_xlsx"},
 "coding": {"read_file","write_file","create_code","execute_code","run_tests"},
 "pid_analysis": {"analyze_image","extract_pid_graph"},
}
PPTX generator: not built (no tool in allow-list).
DOCX "artifact hash": a file cannot contain its own hash. DOCX embeds content_hash (sha256 of canonical spec JSON); the file's artifact_hash lives in the manifest and API/UI.
Additive endpoints beyond the frozen list (non-breaking): GET /api/tasks/{id}/stream, GET /api/knowledge/{file_id}, GET /healthz, GET /readyz.
Sovereignty integrity: if mode=local and any external counter > 0 → status: "AIR-GAP VIOLATED" (never AIR-GAPPED). Confirm with Joy at Step 10.
G8 Contracts (app/contracts/ — write in Step 0, then frozen; changes need Soham+Joy)
python
# models.py (pydantic v2)
InferenceMode = Literal["local","groq"]
TaskState = Literal["INTAKE","CLASSIFY","PLAN","RETRIEVE","TOOL","VERIFY","REPAIR","ARTIFACT","ARTIFACT_VALIDATE","APPROVAL","COMPLETE","FAILED"]
class TaskEvent(BaseModel): type: str; data: dict = {}
class TaskContext(BaseModel): task_id: str; task_type: str|None; workspace: Path; inference_mode: InferenceMode
class ToolRequest(BaseModel): tool: str; args: dict
class PolicyDecision(BaseModel): allowed: bool; tool: str; validated_args: dict = {}; decision_id: str; reason: str|None = None; requires_approval: bool = False
class ToolResult(BaseModel): ok: bool; tool: str; data: dict = {}; stdout: str = ""; stderr: str = ""; exit_code: int|None = None; duration_ms: int = 0; truncated: bool = False; resource_events: list[str] = []; error: str|None = None
class FileRecord(BaseModel): file_id: str; task_id: str|None; kind: Literal["upload","knowledge","pid"]; original_name: str; stored_path: str; size_bytes: int; sha256: str; mime: str
class IngestResult(BaseModel): file_id: str; status: Literal["ok","failed"]; chunks: int = 0; error: str|None = None
class ArtifactManifest(BaseModel): artifact_id: str; task_id: str; artifact_type: Literal["docx","xlsx","graph_json","code_package","pid_overlay"]; path: str; created_at: str; artifact_hash: str; source_evidence_ids: list[str] = []; verification_status: Literal["pending","passed","failed"] = "pending"; metadata: dict = {}
class ValidationReport(BaseModel): passed: bool; checks: list[dict]   # {name, passed, detail}
class PIDGraph(BaseModel): nodes: list[dict]; edges: list[dict]; overlay_image_path: str; narrative: str; confidence_summary: dict
python
# interfaces.py (typing.Protocol). J = implemented by Joy (you stub). S = implemented by you (Joy consumes).
class Orchestrator(Protocol):                                   # J
    def run(self, ctx: TaskContext, user_request: str, file_ids: list[str], services: "Services") -> AsyncIterator[TaskEvent]: ...
    async def approve(self, task_id: str, approver: str, decision: Literal["approve","reject"], note: str|None) -> None: ...
class PolicyValidator(Protocol):                                # J
    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision: ...
class RagIngestor(Protocol):                                    # J
    async def ingest(self, file: FileRecord) -> IngestResult: ...
class PidPipeline(Protocol):                                    # J
    def extract_pid_graph(self, image_path: str) -> PIDGraph: ...
class MlTools(Protocol):                                        # J: ocr_document, search_knowledge_base, retrieve_section, analyze_image, extract_pid_graph
    async def call(self, tool: str, ctx: TaskContext, args: dict) -> dict: ...
class ArtifactValidator(Protocol):                              # J
    async def validate(self, m: ArtifactManifest) -> ValidationReport: ...
class ModelsStatus(Protocol):                                   # J
    def status(self) -> dict: ...   # {active_inference_mode, hardware_profile, models:[{id,type,tasks,provider,model_name,available,resident,memory_estimate_mb}], resident_models:[str], resources:{vram_mb_free,ram_mb_free,disk_mb_free,max_concurrency}}

class ToolRuntime(Protocol):                                    # S
    async def execute(self, ctx: TaskContext, decision: PolicyDecision) -> ToolResult: ...   # raises ToolNotAllowedError
class ArtifactStore(Protocol):                                  # S
    async def register(self, ctx, artifact_type, path: str, source_evidence_ids=[], metadata={}) -> ArtifactManifest: ...
    async def set_verification_status(self, artifact_id: str, status: str) -> None: ...
    async def get(self, artifact_id: str) -> ArtifactManifest: ...
    async def verify_integrity(self, artifact_id: str) -> bool: ...
    async def package_code(self, ctx) -> ArtifactManifest: ...   # zips code/ + results into code_package
class AuditLogger(Protocol):                                    # S
    async def emit(self, category: str, component: str, action: str, status: str = "info", task_id: str|None = None, details: dict = {}) -> None: ...
class Sovereignty(Protocol):                                    # S
    async def record_external_call(self, provider: str, bytes_out: int, bytes_in: int) -> None: ...   # Joy's GroqProvider calls this per request
    async def snapshot(self) -> dict: ...
@dataclass
class Services: runtime: ToolRuntime; artifacts: ArtifactStore; audit: AuditLogger; sovereignty: Sovereignty; policy: PolicyValidator; ml_tools: MlTools; artifact_validator: ArtifactValidator; workspace_root: Path

Errors (app/errors.py): AppError(code, http_status, message) + subclasses ToolNotAllowedError(403 TOOL_NOT_ALLOWED), PathRejectedError(400 PATH_REJECTED), SandboxUnavailableError(503 SANDBOX_UNAVAILABLE), ArtifactCorruptError(500 ARTIFACT_CORRUPT), EgressDeniedError. Also NOT_FOUND 404, VALIDATION_ERROR 422, CONFLICT 409, PAYLOAD_TOO_LARGE 413, UNSUPPORTED_MEDIA 415, TASK_CAPACITY 429, INTERNAL 500.

G9 Events and audit

Event envelope (persisted in task_events, streamed via SSE): {"id": <seq int>, "task_id", "ts", "type", "inference_mode", "data": {...}}. SSE frame: id: <seq> · event: <type> · data: <envelope json>.

type	data	emitted by
task_created	{task_id, inference_mode}	runner
state_changed	{state}	orchestrator
message	{text}	orchestrator
plan	{steps:[str]}	orchestrator
model_selected	{model_id, model_name, provider}	orchestrator
tool_proposed	{tool, args}	orchestrator
policy_decision	{tool, allowed, reason, decision_id}	orchestrator
tool_result	{tool, ok, summary, duration_ms}	orchestrator
retrieval	{chunks:[{chunk_id, document_id, page, section, source_hash, text}]}	orchestrator
verification	{status: pending|passed|failed, details}	orchestrator
repair	{attempt, reason}	orchestrator
artifact_created	{artifact_id, artifact_type}	orchestrator
artifact_validation	{artifact_id, passed, checks}	orchestrator
pid_graph	{graph}	orchestrator
approval_requested	{artifact_ids, summary}	orchestrator
approved / rejected	{approver, note}	runner
completed	{final_result}	orchestrator
failed	{error:{code,message}}	orchestrator or runner
completed/failed are terminal (stream closes after them).		

Runner state mapping on each event: state_changed→current_state; plan→plan; model_selected→model_used; tool_result→append to tool_calls; retrieval→extend retrieved_chunks; verification→verification_status; pid_graph→pid_graph; approval_requested→state APPROVAL; completed→final_result, state COMPLETE; failed→append errors, state FAILED; classify result: if data.task_type present in state_changed, set task_type.

Audit categories (enum): TASK_CREATED MODEL_SELECTED PROVIDER_CALL RETRIEVAL TOOL_PROPOSED POLICY_ALLOWED POLICY_DENIED TOOL_EXECUTED SANDBOX_STARTED SANDBOX_BLOCKED_NETWORK VERIFICATION_STARTED VERIFICATION_FAILED REPAIR_STARTED ARTIFACT_CREATED ARTIFACT_VALIDATION_FAILED ARTIFACT_VALIDATED APPROVAL_REQUESTED APPROVED TASK_COMPLETED TASK_FAILED (+ yours: FILE_UPLOADED INGEST_STARTED INGEST_FAILED EGRESS_DENIED ARTIFACT_CORRUPT). Who emits (emit at the source, no duplicates):

Runner maps events→audit: task_created→TASK_CREATED · model_selected→MODEL_SELECTED · retrieval→RETRIEVAL · tool_proposed→TOOL_PROPOSED · policy_decision→POLICY_ALLOWED/DENIED · verification(pending)→VERIFICATION_STARTED, (failed)→VERIFICATION_FAILED · repair→REPAIR_STARTED · artifact_validation→ARTIFACT_VALIDATED/ARTIFACT_VALIDATION_FAILED · approval_requested→APPROVAL_REQUESTED · completed→TASK_COMPLETED · failed→TASK_FAILED.
Runtime: TOOL_EXECUTED, SANDBOX_*, and POLICY_DENIED for its own rejections. Artifact store: ARTIFACT_CREATED, ARTIFACT_CORRUPT. Approve endpoint: APPROVED. Joy's provider: PROVIDER_CALL. Audit row: task_id, ts, inference_mode (required), category, component, action, status (ok|denied|error|info), details(json). Redact before write: dict keys matching (?i)key|token|secret|authorization|password → "[REDACTED]"; strings matching gsk_[A-Za-z0-9]+ → [REDACTED]. Tool args in audit: store arg names + sizes, not file contents.
G10 Database (app/core/schema.sql, applied idempotently at startup; PRAGMA journal_mode=WAL; foreign_keys=ON; busy_timeout=5000)
sql
CREATE TABLE IF NOT EXISTS schema_version(v INTEGER);
CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, user_request TEXT NOT NULL, task_type TEXT, plan TEXT DEFAULT '[]',
 current_state TEXT NOT NULL DEFAULT 'INTAKE', inference_mode TEXT NOT NULL, model_used TEXT, tool_calls TEXT DEFAULT '[]',
 retrieved_chunks TEXT DEFAULT '[]', pid_graph TEXT, errors TEXT DEFAULT '[]', verification_status TEXT DEFAULT 'pending',
 final_result TEXT, requires_human_approval INTEGER DEFAULT 1, approved_by TEXT, approval_note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_task ON task_events(task_id, seq);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, ts TEXT NOT NULL, inference_mode TEXT NOT NULL,
 category TEXT NOT NULL, component TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, details TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_audit_task ON audit_log(task_id, id);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TABLE IF NOT EXISTS files(file_id TEXT PRIMARY KEY, task_id TEXT, kind TEXT NOT NULL, original_name TEXT NOT NULL, stored_path TEXT NOT NULL,
 size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, mime TEXT, ingest_status TEXT, ingest_error TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, artifact_type TEXT NOT NULL, path TEXT NOT NULL,
 artifact_hash TEXT NOT NULL, source_evidence_ids TEXT DEFAULT '[]', verification_status TEXT DEFAULT 'pending', metadata TEXT DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sovereignty_counters(id INTEGER PRIMARY KEY CHECK(id=1), external_api_calls INTEGER DEFAULT 0, external_connections INTEGER DEFAULT 0,
 external_bytes_out INTEGER DEFAULT 0, external_bytes_in INTEGER DEFAULT 0, denied_connections INTEGER DEFAULT 0, since TEXT);

JSON columns store JSON text. Counter updates are atomic (SET x = x + ?).

G11 API contract (DEFAULTS until Step 3 reconciles with the frontend; then frozen as contract v1)

Errors everywhere: {"error":{"code","message","request_id","task_id"?}} with proper HTTP status.

POST /api/chat body {message:str(1..MAX_MESSAGE_CHARS), file_ids?:[str], knowledge_ids?:[str]} → creates task, starts runner in background, responds text/event-stream (first event task_created), header X-Task-Id. Client disconnect MUST NOT cancel the task. 429 if active tasks ≥ MAX_ACTIVE_TASKS.
GET /api/tasks/{id}/stream (additive) → same SSE; honors Last-Event-ID (replay seq > id, then live); for finished tasks replays then closes.
GET /api/tasks/{id} → {task_id,user_request,task_type,plan,current_state,inference_mode,model_used,tool_calls,retrieved_chunks,artifacts:[ArtifactManifest],pid_graph,errors,verification_status,final_result,requires_human_approval,approved_by,created_at,updated_at}.
GET /api/tasks/{id}/timeline → {task_id, entries:[audit rows ordered by id]} (audit timeline; SSE is the live feed).
POST /api/tasks/{id}/approve body {approver:str, decision:"approve"|"reject", note?:str} → 200 {task_id, current_state, approved_by}; 409 unless state==APPROVAL (also on repeat).
POST /api/files/upload multipart repeated field file, optional form task_id → {files:[{file_id,name,size,sha256,mime,kind}]}.
POST /api/knowledge/upload multipart repeated file → {files:[{file_id,name,size,sha256,mime,ingest_status}]}; ingestion runs in background.
GET /api/knowledge/{file_id} (additive) → {file_id,name,ingest_status,ingest_error}.
GET /api/artifacts/{id} → manifest JSON incl. download_url; ?download=1 streams the file (after integrity re-hash).
GET /api/models → Joy's ModelsStatus.status() passthrough (shape in G8).
GET /api/monitoring/sovereignty → shape below.
POST /api/pid/analyze multipart file (image) → {task_id, graph:{nodes,edges,narrative,confidence_summary,overlay_artifact_id}, artifact_ids:[...]}.
GET /healthz → {ok:true}; GET /readyz → per-check {sqlite,docker,sandbox_image,qdrant,ollama} each ok|fail; 503 if sqlite/docker/sandbox_image fail (qdrant/ollama reported only).

Sovereignty response:

json
// local
{"inference_mode":"local","status":"AIR-GAPPED","provider":"ollama","network_policy":"deny_all","internet_access":"BLOCKED","sandbox_network":"disabled",
 "external_api_calls":0,"external_connections":0,"external_bytes_out":0,"external_bytes_in":0,"denied_connection_attempts":0,"since":"<ts>"}
// groq
{"inference_mode":"groq","status":"EXTERNAL INFERENCE ACTIVE","provider":"Groq","network_policy":"groq_endpoint_only","internet_access":"ALLOWED (Groq endpoint only)","sandbox_network":"disabled",
 "external_api_calls":12,"external_connections":1,"external_bytes_out":0,"external_bytes_in":0,"denied_connection_attempts":0,"since":"<ts>"}

Mode comes from settings.INFERENCE_MODE only.

G12 Workspace layout

DATA_DIR/workspaces/{task_id}/{inputs,outputs,code}/. inputs/ = copies of task files; outputs/ = generated artifacts; code/ = the ONLY dir mounted into the sandbox (at /work). Standalone uploads: DATA_DIR/uploads/{file_id}/{file_id}.{ext} (stored under uuid, original name kept as metadata only). P&ID: DATA_DIR/pid/{file_id}/.