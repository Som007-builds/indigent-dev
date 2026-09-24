# Indigent — Platform Backend Build PRD (Soham's scope)

For: Codex / AI coding agent. Owner: Soham. Counterpart: Joy (AI control plane, out of your scope).
Source specs: "Backend Build PRD v1.1" + "Backend Responsibilities". Everything needed is restated here.

## HOW TO USE (human)
1. Fill the FILL-INS block. 2. Copy section `## G` (all of it) into `AGENTS.md` at repo root (Codex reads it automatically).
3. Run ONE step per fresh agent session, in order. Paste only that step's `PROMPT` (≈50 words). Never paste this whole file.
4. Agent reads only `## G` subsections listed in the step's `Needs:` plus its own `## STEP N` (use `grep -n "^## " build.prd.md` then `sed -n`).
5. Review the agent's 10-line report + `pytest -q` before starting the next step.

## FILL-INS (edit before Step 0; agent must not guess these)
```
OS / hardware profile .........   macOS Apple Silicon -> LOCAL_HARDWARE_PROFILE=mac_silicon  
Python ........................   (default 3.11)
Docker installed & running .... yes   (required for sandbox; if no, sandbox steps fail loudly by design)
FRONTEND_REPO_PATH ............ <path to React repo>   (Step 3 only)
FRONTEND_DEV_URL .............. default http://localhost:5173 (unverified; Vite default)
Monorepo  ..................... default: one repo `indigent/`;  
```

---

## G — GLOBAL CONTEXT (copy to AGENTS.md)

### G1 Product
Air-gapped AI assistant for refineries/PSUs/defence manufacturing. Data (P&IDs, financials, vendor terms, designs) must never leave the machine. Runs on ONE local machine: plan → use tools → read documents/images → write real deliverables (DOCX/XLSX/code), with "nothing leaves this device" proven live in a Sovereignty Monitor. Stack: React frontend → FastAPI → agent orchestrator → policy layer → tools/sandbox; Ollama (local models), Qdrant (vectors), SQLite (state+audit), Docker (sandbox). Groq API exists ONLY as an opt-in dev/test inference path.

### G2 Ownership boundary (never cross)
- **You (Soham) own mechanisms**: API gateway, request/response schemas, SQLite persistence, SSE, files/workspaces, artifact storage/lifecycle, audit persistence, tool execution plumbing, Docker sandbox, knowledge/P&ID API plumbing, models/sovereignty API exposure, config/compose, logging, health, infra tests, frontend contract.
- **Joy owns intelligence**: `app/providers/`, `app/agent/` (orchestrator, router, resource manager, model registry), `app/policy/` (policy validation, allow-lists), `app/rag/`, `app/artifact_validation/`, P&ID ML internals. **Do not create or edit files in these dirs.** You code against the interfaces in G8 and use stubs in `app/stubs/`.
- Joint: end-to-end integration, security tests, demo reliability.

### G3 Security invariants (violating any = bug)
1. LLM output never authorizes an action; every tool call needs a `PolicyDecision(allowed=True)` from Joy's validator before your runtime executes it.
2. Every filesystem path derived from model/user input goes through `safe_join()` (Step 4).
3. Sandbox: `--network=none` always (local AND groq mode). If Docker is unavailable → fail loudly (`SANDBOX_UNAVAILABLE`). **Never fall back to host subprocess.**
4. No Groq fallback, no mode switching. `INFERENCE_MODE` (`local|groq`) is read from config only, default `local`, never inferred.
5. Groq mode must never be shown as AIR-GAPPED.
6. Secrets (`GROQ_API_KEY`, anything matching key/token/secret/authorization) never logged, never in audit, never in API responses, never committed.
7. Unauthorized tools fail closed and are audited. Audit log is append-only.
8. Backend binds `127.0.0.1` only. Code and tests make zero external network calls.
9. Bounded everything: timeouts, sizes, output, concurrency.

### G4 Stack, tooling, commands
- Python 3.11+, FastAPI, uvicorn, pydantic v2 + pydantic-settings, aiosqlite, sse-starlette, python-multipart, docker (SDK), python-docx, openpyxl, Pillow, httpx, pytest, pytest-asyncio, ruff. Use latest stable; after Step 0 write resolved versions to `requirements.lock` (`pip freeze`).
- Do NOT import `ollama`, `groq`, or any LLM SDK anywhere (Joy's `providers/` only).
- Commands: `ruff check .` · `pytest -q` · `pytest -q -m "not docker"` (no Docker) · `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Style: type hints, async I/O, small modules, no dead code, no TODOs left silently (log in `docs/decisions.md`).
- **Rule on gaps**: if this doc is silent → use the DEFAULT in G7; if none → STOP and ask Soham. Record every deviation/choice in `docs/decisions.md` (1 line each).
- Report format after each step (≤10 lines): files changed · tests run/passed · deviations · open questions.

### G5 Repo layout
```
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
```
Joy wiring switch: env `JOY_MODULES=stub|real` (default `stub`). `deps.py` picks stub or real EXPLICITLY (no try-import fallback).

### G6 Config (`app/config.py`, pydantic-settings, `.env.example` has no secrets)
| Var | Default | Notes |
|---|---|---|
| INFERENCE_MODE | local | must be `local` or `groq`, else refuse to start |
| LOCAL_HARDWARE_PROFILE | mac_silicon | `mac_silicon` \| `rtx_3050a_4gb` |
| GROQ_API_KEY | (empty) | only read by Joy's provider; never logged |
| JOY_MODULES | stub | stub \| real |
| API_HOST / API_PORT | 127.0.0.1 / 8000 | |
| CORS_ORIGINS | http://localhost:5173 | comma list |
| DATA_DIR | ./data | Mac+Docker Desktop: must be under a Docker-shared path (e.g. inside home dir) |
| OLLAMA_BASE_URL | http://localhost:11434 | readiness only |
| QDRANT_URL | http://localhost:6333 | readiness + passed to Joy |
| MAX_UPLOAD_MB / MAX_PID_IMAGE_MB | 50 / 25 | |
| MAX_MESSAGE_CHARS | 20000 | |
| MAX_ACTIVE_TASKS | 2 | more → 429 |
| PER_TOOL_TIMEOUT_S | 30 | |
| MODEL_GENERATION_TIMEOUT_S | 60 | (Joy uses; exposed) |
| HARD_TASK_TIMEOUT_S | 300 | excludes time in APPROVAL |
| APPROVAL_TIMEOUT_S | 86400 | |
| PID_TIMEOUT_S | 120 | |
| SANDBOX_IMAGE | indigent-sandbox:1 | |
| SANDBOX_MEM_MB / SANDBOX_CPUS / SANDBOX_PIDS | 256 / 1 / 64 | |
| SANDBOX_OUTPUT_LIMIT_KB | 64 | per stream |
| WORKSPACE_TTL_HOURS | 24 | scratch cleanup only; outputs+audit kept |
| LOG_LEVEL | INFO | |
Startup: log mode + profile. If mode=groq log WARNING "EXTERNAL INFERENCE ACTIVE". Every HTTP response carries header `X-Inference-Mode: <mode>`.

### G7 Locked decisions & defaults
- Backend runs on the HOST (not in Docker): Ollama needs host GPU/Metal; sandbox needs the Docker socket. Compose runs Qdrant only (Step 9).
- No auth (IAM out of scope). `approver` is free text.
- Ids: task_id = uuid4 str; file_id = uuid4 hex; artifact_id = uuid4 str. Timestamps: ISO-8601 UTC (`2026-09-25T10:00:00Z`).
- Allowed upload types: `.pdf .png .jpg .jpeg .tif .tiff .docx .xlsx .pptx .txt .md .csv .json`. Verify magic bytes for pdf/images/office (zip). P&ID images: png/jpg/jpeg/tif/tiff only.
- Task types: `inspection`, `coding`, `pid_analysis` (task_type set by orchestrator `CLASSIFY`; before that `null`).
- ALLOWED_TOOLS (seed for `app/policy/allowlist.py`, Joy may edit later):
```python
ALLOWED_TOOLS = {
    "inspection": {
        "read_file",
        "ocr_document",
        "search_knowledge_base",
        "retrieve_section",
        "create_docx",
        "create_xlsx",
    },
    "coding": {"read_file", "write_file", "create_code", "execute_code", "run_tests"},
    "pid_analysis": {"analyze_image", "extract_pid_graph"},
}
```
- PPTX generator: not built (no tool in allow-list).
- DOCX "artifact hash": a file cannot contain its own hash. DOCX embeds `content_hash` (sha256 of canonical spec JSON); the file's `artifact_hash` lives in the manifest and API/UI.
- Additive endpoints beyond the frozen list (non-breaking): `GET /api/tasks/{id}/stream`, `GET /api/knowledge/{file_id}`, `GET /healthz`, `GET /readyz`.
- Sovereignty integrity: if mode=local and any external counter > 0 → `status: "AIR-GAP VIOLATED"` (never AIR-GAPPED). Confirm with Joy at Step 10.

### G8 Contracts (`app/contracts/` — write in Step 0, then frozen; changes need Soham+Joy)
```python
# models.py (pydantic v2)
InferenceMode = Literal["local", "groq"]
TaskState = Literal[
    "INTAKE",
    "CLASSIFY",
    "PLAN",
    "RETRIEVE",
    "TOOL",
    "VERIFY",
    "REPAIR",
    "ARTIFACT",
    "ARTIFACT_VALIDATE",
    "APPROVAL",
    "COMPLETE",
    "FAILED",
]


class TaskEvent(BaseModel):
    type: str
    data: dict = {}


class TaskContext(BaseModel):
    task_id: str
    task_type: str | None
    workspace: Path
    inference_mode: InferenceMode


class ToolRequest(BaseModel):
    tool: str
    args: dict


class PolicyDecision(BaseModel):
    allowed: bool
    tool: str
    validated_args: dict = {}
    decision_id: str
    reason: str | None = None
    requires_approval: bool = False


class ToolResult(BaseModel):
    ok: bool
    tool: str
    data: dict = {}
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    truncated: bool = False
    resource_events: list[str] = []
    error: str | None = None


class FileRecord(BaseModel):
    file_id: str
    task_id: str | None
    kind: Literal["upload", "knowledge", "pid"]
    original_name: str
    stored_path: str
    size_bytes: int
    sha256: str
    mime: str


class IngestResult(BaseModel):
    file_id: str
    status: Literal["ok", "failed"]
    chunks: int = 0
    error: str | None = None


class ArtifactManifest(BaseModel):
    artifact_id: str
    task_id: str
    artifact_type: Literal["docx", "xlsx", "graph_json", "code_package", "pid_overlay"]
    path: str
    created_at: str
    artifact_hash: str
    source_evidence_ids: list[str] = []
    verification_status: Literal["pending", "passed", "failed"] = "pending"
    metadata: dict = {}


class ValidationReport(BaseModel):
    passed: bool
    checks: list[dict]  # {name, passed, detail}


class PIDGraph(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    overlay_image_path: str
    narrative: str
    confidence_summary: dict
```
```python
# interfaces.py (typing.Protocol). J = implemented by Joy (you stub). S = implemented by you (Joy consumes).
class Orchestrator(Protocol):  # J
    def run(
        self, ctx: TaskContext, user_request: str, file_ids: list[str], services: "Services"
    ) -> AsyncIterator[TaskEvent]: ...
    async def approve(
        self, task_id: str, approver: str, decision: Literal["approve", "reject"], note: str | None
    ) -> None: ...


class PolicyValidator(Protocol):  # J
    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision: ...


class RagIngestor(Protocol):  # J
    async def ingest(self, file: FileRecord) -> IngestResult: ...


class PidPipeline(Protocol):  # J
    def extract_pid_graph(self, image_path: str) -> PIDGraph: ...


class MlTools(
    Protocol
):  # J: ocr_document, search_knowledge_base, retrieve_section, analyze_image, extract_pid_graph
    async def call(self, tool: str, ctx: TaskContext, args: dict) -> dict: ...


class ArtifactValidator(Protocol):  # J
    async def validate(self, m: ArtifactManifest) -> ValidationReport: ...


class ModelsStatus(Protocol):  # J
    def status(
        self,
    ) -> dict: ...  # {active_inference_mode, hardware_profile, models:[{id,type,tasks,provider,model_name,available,resident,memory_estimate_mb}], resident_models:[str], resources:{vram_mb_free,ram_mb_free,disk_mb_free,max_concurrency}}


class ToolRuntime(Protocol):  # S
    async def execute(
        self, ctx: TaskContext, decision: PolicyDecision
    ) -> ToolResult: ...  # raises ToolNotAllowedError


class ArtifactStore(Protocol):  # S
    async def register(
        self, ctx, artifact_type, path: str, source_evidence_ids=[], metadata={}
    ) -> ArtifactManifest: ...
    async def set_verification_status(self, artifact_id: str, status: str) -> None: ...
    async def get(self, artifact_id: str) -> ArtifactManifest: ...
    async def verify_integrity(self, artifact_id: str) -> bool: ...
    async def package_code(
        self, ctx
    ) -> ArtifactManifest: ...  # zips code/ + results into code_package


class AuditLogger(Protocol):  # S
    async def emit(
        self,
        category: str,
        component: str,
        action: str,
        status: str = "info",
        task_id: str | None = None,
        details: dict = {},
    ) -> None: ...


class Sovereignty(Protocol):  # S
    async def record_external_call(
        self, provider: str, bytes_out: int, bytes_in: int
    ) -> None: ...  # Joy's GroqProvider calls this per request
    async def snapshot(self) -> dict: ...


@dataclass
class Services:
    runtime: ToolRuntime
    artifacts: ArtifactStore
    audit: AuditLogger
    sovereignty: Sovereignty
    policy: PolicyValidator
    ml_tools: MlTools
    artifact_validator: ArtifactValidator
    workspace_root: Path
```
Errors (`app/errors.py`): `AppError(code, http_status, message)` + subclasses `ToolNotAllowedError(403 TOOL_NOT_ALLOWED)`, `PathRejectedError(400 PATH_REJECTED)`, `SandboxUnavailableError(503 SANDBOX_UNAVAILABLE)`, `ArtifactCorruptError(500 ARTIFACT_CORRUPT)`, `EgressDeniedError`. Also NOT_FOUND 404, VALIDATION_ERROR 422, CONFLICT 409, PAYLOAD_TOO_LARGE 413, UNSUPPORTED_MEDIA 415, TASK_CAPACITY 429, INTERNAL 500.

### G9 Events and audit
Event envelope (persisted in `task_events`, streamed via SSE): `{"id": <seq int>, "task_id", "ts", "type", "inference_mode", "data": {...}}`. SSE frame: `id: <seq>` · `event: <type>` · `data: <envelope json>`.

| type | data | emitted by |
|---|---|---|
| task_created | {task_id, inference_mode} | runner |
| state_changed | {state} | orchestrator |
| message | {text} | orchestrator |
| plan | {steps:[str]} | orchestrator |
| model_selected | {model_id, model_name, provider} | orchestrator |
| tool_proposed | {tool, args} | orchestrator |
| policy_decision | {tool, allowed, reason, decision_id} | orchestrator |
| tool_result | {tool, ok, summary, duration_ms} | orchestrator |
| retrieval | {chunks:[{chunk_id, document_id, page, section, source_hash, text}]} | orchestrator |
| verification | {status: pending\|passed\|failed, details} | orchestrator |
| repair | {attempt, reason} | orchestrator |
| artifact_created | {artifact_id, artifact_type} | orchestrator |
| artifact_validation | {artifact_id, passed, checks} | orchestrator |
| pid_graph | {graph} | orchestrator |
| approval_requested | {artifact_ids, summary} | orchestrator |
| approved / rejected | {approver, note} | runner |
| completed | {final_result} | orchestrator |
| failed | {error:{code,message}} | orchestrator or runner |
`completed`/`failed` are terminal (stream closes after them).

Runner state mapping on each event: `state_changed`→`current_state`; `plan`→`plan`; `model_selected`→`model_used`; `tool_result`→append to `tool_calls`; `retrieval`→extend `retrieved_chunks`; `verification`→`verification_status`; `pid_graph`→`pid_graph`; `approval_requested`→state APPROVAL; `completed`→`final_result`, state COMPLETE; `failed`→append `errors`, state FAILED; classify result: if `data.task_type` present in `state_changed`, set `task_type`.

Audit categories (enum): TASK_CREATED MODEL_SELECTED PROVIDER_CALL RETRIEVAL TOOL_PROPOSED POLICY_ALLOWED POLICY_DENIED TOOL_EXECUTED SANDBOX_STARTED SANDBOX_BLOCKED_NETWORK VERIFICATION_STARTED VERIFICATION_FAILED REPAIR_STARTED ARTIFACT_CREATED ARTIFACT_VALIDATION_FAILED ARTIFACT_VALIDATED APPROVAL_REQUESTED APPROVED TASK_COMPLETED TASK_FAILED (+ yours: FILE_UPLOADED INGEST_STARTED INGEST_FAILED EGRESS_DENIED ARTIFACT_CORRUPT).
Who emits (emit at the source, no duplicates):
- Runner maps events→audit: task_created→TASK_CREATED · model_selected→MODEL_SELECTED · retrieval→RETRIEVAL · tool_proposed→TOOL_PROPOSED · policy_decision→POLICY_ALLOWED/DENIED · verification(pending)→VERIFICATION_STARTED, (failed)→VERIFICATION_FAILED · repair→REPAIR_STARTED · artifact_validation→ARTIFACT_VALIDATED/ARTIFACT_VALIDATION_FAILED · approval_requested→APPROVAL_REQUESTED · completed→TASK_COMPLETED · failed→TASK_FAILED.
- Runtime: TOOL_EXECUTED, SANDBOX_*, and POLICY_DENIED for its own rejections. Artifact store: ARTIFACT_CREATED, ARTIFACT_CORRUPT. Approve endpoint: APPROVED. Joy's provider: PROVIDER_CALL.
Audit row: `task_id, ts, inference_mode (required), category, component, action, status (ok|denied|error|info), details(json)`. Redact before write: dict keys matching `(?i)key|token|secret|authorization|password` → `"[REDACTED]"`; strings matching `gsk_[A-Za-z0-9]+` → `[REDACTED]`. Tool args in audit: store arg names + sizes, not file contents.

### G10 Database (`app/core/schema.sql`, applied idempotently at startup; `PRAGMA journal_mode=WAL; foreign_keys=ON; busy_timeout=5000`)
```sql
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
```
JSON columns store JSON text. Counter updates are atomic (`SET x = x + ?`).

### G11 API contract (DEFAULTS until Step 3 reconciles with the frontend; then frozen as `contract v1`)
Errors everywhere: `{"error":{"code","message","request_id","task_id"?}}` with proper HTTP status.
- `POST /api/chat` body `{message:str(1..MAX_MESSAGE_CHARS), file_ids?:[str], knowledge_ids?:[str]}` → creates task, starts runner in background, responds `text/event-stream` (first event `task_created`), header `X-Task-Id`. Client disconnect MUST NOT cancel the task. 429 if active tasks ≥ MAX_ACTIVE_TASKS.
- `GET /api/tasks/{id}/stream` (additive) → same SSE; honors `Last-Event-ID` (replay `seq > id`, then live); for finished tasks replays then closes.
- `GET /api/tasks/{id}` → `{task_id,user_request,task_type,plan,current_state,inference_mode,model_used,tool_calls,retrieved_chunks,artifacts:[ArtifactManifest],pid_graph,errors,verification_status,final_result,requires_human_approval,approved_by,created_at,updated_at}`.
- `GET /api/tasks/{id}/timeline` → `{task_id, entries:[audit rows ordered by id]}` (audit timeline; SSE is the live feed).
- `POST /api/tasks/{id}/approve` body `{approver:str, decision:"approve"|"reject", note?:str}` → 200 `{task_id, current_state, approved_by}`; 409 unless state==APPROVAL (also on repeat).
- `POST /api/files/upload` multipart repeated field `file`, optional form `task_id` → `{files:[{file_id,name,size,sha256,mime,kind}]}`.
- `POST /api/knowledge/upload` multipart repeated `file` → `{files:[{file_id,name,size,sha256,mime,ingest_status}]}`; ingestion runs in background.
- `GET /api/knowledge/{file_id}` (additive) → `{file_id,name,ingest_status,ingest_error}`.
- `GET /api/artifacts/{id}` → manifest JSON incl. `download_url`; `?download=1` streams the file (after integrity re-hash).
- `GET /api/models` → Joy's `ModelsStatus.status()` passthrough (shape in G8).
- `GET /api/monitoring/sovereignty` → shape below.
- `POST /api/pid/analyze` multipart `file` (image) → `{task_id, graph:{nodes,edges,narrative,confidence_summary,overlay_artifact_id}, artifact_ids:[...]}`.
- `GET /healthz` → `{ok:true}`; `GET /readyz` → per-check `{sqlite,docker,sandbox_image,qdrant,ollama}` each `ok|fail`; 503 if sqlite/docker/sandbox_image fail (qdrant/ollama reported only).

Sovereignty response:
```json
// local
{"inference_mode":"local","status":"AIR-GAPPED","provider":"ollama","network_policy":"deny_all","internet_access":"BLOCKED","sandbox_network":"disabled",
 "external_api_calls":0,"external_connections":0,"external_bytes_out":0,"external_bytes_in":0,"denied_connection_attempts":0,"since":"<ts>"}
// groq
{"inference_mode":"groq","status":"EXTERNAL INFERENCE ACTIVE","provider":"Groq","network_policy":"groq_endpoint_only","internet_access":"ALLOWED (Groq endpoint only)","sandbox_network":"disabled",
 "external_api_calls":12,"external_connections":1,"external_bytes_out":0,"external_bytes_in":0,"denied_connection_attempts":0,"since":"<ts>"}
```
Mode comes from `settings.INFERENCE_MODE` only.

### G12 Workspace layout
`DATA_DIR/workspaces/{task_id}/{inputs,outputs,code}/`. `inputs/` = copies of task files; `outputs/` = generated artifacts; `code/` = the ONLY dir mounted into the sandbox (at `/work`). Standalone uploads: `DATA_DIR/uploads/{file_id}/{file_id}.{ext}` (stored under uuid, original name kept as metadata only). P&ID: `DATA_DIR/pid/{file_id}/`.

---

## STEP 0 — Skeleton, config, contracts, stubs, logging, errors
Needs: G3 G4 G5 G6 G8 G9 G11 · Day 1
**Build**
- Repo layout G5 (empty modules ok), `pyproject.toml`, `.gitignore` (`.env`, `data/`, `__pycache__`), `.env.example` (all G6 vars, no secrets).
- `config.py` (validate INFERENCE_MODE; refuse start otherwise), `errors.py` + global exception handler → G11 error format, `logging_setup.py` (JSON lines to stdout + `DATA_DIR/logs/app.log`; contextvars `request_id`,`task_id`; secret-redaction filter), middleware: request id (`X-Request-ID`, generated if absent), `X-Inference-Mode` header, CORS from config.
- `contracts/models.py`, `contracts/interfaces.py` exactly per G8.
- `stubs/*`: implement every J interface. `StubOrchestrator` scenarios chosen by `user_request` prefix: `stub:happy` (INTAKE→CLASSIFY(task_type=inspection)→PLAN→RETRIEVE→TOOL→VERIFY→ARTIFACT(create a real small docx via services)→ARTIFACT_VALIDATE→APPROVAL(wait for approve())→COMPLETE, emitting the matching events with ~50 ms gaps), `stub:fail` (emits `failed`), `stub:slow` (sleeps 400 s), `stub:hang_approval`, `stub:tool` (one tool through policy+runtime), default = happy. `StubPolicy`: allow iff tool in ALLOWED_TOOLS[ctx.task_type], else deny; returns validated_args=args. `StubMlTools`/`StubRag`/`StubPid`/`StubModelsStatus`/`StubArtifactValidator` return canned valid data (validator passes).
- `deps.py`: builds `Services` from `JOY_MODULES`; `main.py`: app factory with `/healthz` only.
**Done when**: `uvicorn` starts; `GET /healthz` 200 with both headers; bad `INFERENCE_MODE=x` refuses to start (test); `ruff` + `pytest` green; log lines are JSON and never contain a fake `gsk_test123` secret pushed through the logger (test).
**PROMPT**
```
Implement STEP 0 of build.prd.md. Read only `## G` subsections listed in "Needs" and `## STEP 0` (grep -n "^## " then sed -n). Create only files in G5 outside Joy dirs. Follow G3/G4 rules; if spec is silent use G7 default or ask. Finish with ruff + pytest green. Report ≤10 lines per G4.
```

## STEP 1 — SQLite persistence + audit infrastructure
Needs: G3 G8 G9 G10 · Day 1–2
**Build**
- `core/db.py`: aiosqlite helper (connection factory, pragmas, apply `schema.sql`, `schema_version`=1). `core/repo.py`: typed functions: create_task, get_task, update_task_fields, append_json_field, insert_event (returns seq), list_events(task_id, after_seq), insert_file/get_file/update_ingest, insert_artifact/get_artifact/list_artifacts(task_id), audit insert/list, counters get/increment.
- `core/audit.py`: `AuditLoggerImpl` per G9 (redaction, mandatory `inference_mode` from settings, category must be in enum else raise). No update/delete API.
- Startup recovery: tasks with state not in (COMPLETE, FAILED) → set FAILED, append error `{code:"INTERRUPTED",message:"backend restarted"}`, audit TASK_FAILED.
**Done when** tests prove: schema idempotent; JSON fields round-trip; audit UPDATE/DELETE raises (trigger); secrets redacted (`{"api_key":"x"}`, `gsk_abc` in a string); missing/invalid category rejected; inference_mode always present; startup recovery flips a stuck task; counters increment atomically under 50 concurrent calls.
**PROMPT**
```
Implement STEP 1 of build.prd.md (read G-sections in "Needs" + `## STEP 1` only). SQL must match G10 exactly. Wire audit into deps.py Services. Write tests listed in "Done when". ruff+pytest green. Report ≤10 lines.
```

## STEP 2 — Task API, EventBus, TaskRunner, SSE, /api/chat (against stubs)
Needs: G3 G6 G8 G9 G11 · Day 1–2
**Build**
- `core/events.py` `EventBus`: `publish(task_id, type, data)` = persist to `task_events` FIRST (get seq) then fan out to subscriber queues; `subscribe(task_id, after_seq)` = register queue, replay DB rows `seq > after_seq`, then drain live items skipping `seq <= last_replayed` (no gaps, no duplicates).
- `core/taskrunner.py` `TaskRunner`: `start(user_request, file_ids)` → checks capacity (429), creates task row (mode from settings, workspace dirs per G12, copy referenced files into `inputs/`), publishes `task_created`, spawns `asyncio.create_task(_run)` stored in a registry. `_run` iterates `orchestrator.run(...)` using per-event `asyncio.wait_for(anext(gen), remaining)`: remaining = HARD_TASK_TIMEOUT_S − active_elapsed; while task state == APPROVAL use APPROVAL_TIMEOUT_S and don't count that time as active. Each event: apply G9 state mapping → persist task fields → audit mapping → publish. On timeout: `aclose()` generator, publish `failed{code:TASK_TIMEOUT}`. On exception: `failed{code:INTERNAL}` (message sanitized, no stack to client; stack to logs). If generator ends without a terminal event → `failed{code:NO_TERMINAL_EVENT}`. Always release capacity slot in `finally`.
- `api/chat.py`, `api/tasks.py` per G11: chat SSE (sse-starlette, ping every 15 s, headers `X-Task-Id`), `/stream` with `Last-Event-ID`, task GET (join artifacts), timeline (audit), approve: 409 unless APPROVAL; persist `approved_by/approval_note`, publish `approved|rejected`, emit APPROVED audit, THEN call `orchestrator.approve(...)`.
**Done when** tests (httpx ASGI, stub orchestrator): happy stream has all expected event types in order and closes after `completed`; client disconnect mid-stream → task still reaches COMPLETE; `Last-Event-ID` replay has no gaps/dupes; `stub:fail` → FAILED + TASK_FAILED audit; `stub:slow` with `HARD_TASK_TIMEOUT_S=2` → `failed` TASK_TIMEOUT; approval waiting is not counted against hard timeout; approve twice → second 409; approve when not in APPROVAL → 409; capacity 429; oversize/empty message → 422; GET task includes `inference_mode`; timeline lists TASK_CREATED…TASK_COMPLETED.
**PROMPT**
```
Implement STEP 2 of build.prd.md (only "Needs" G-sections + `## STEP 2`). Use stubs; do not touch Joy dirs. Task must run independent of the HTTP request. Write every test in "Done when". ruff+pytest green. Report ≤10 lines.
```

## STEP 3 — Frontend contract reconciliation & freeze
Needs: G4 G11 · Day 1 (run right after Step 2; may need FILL-IN FRONTEND_REPO_PATH)
**Build**
- Read-only inspect the frontend repo: find every network call (`fetch`, `axios`, `EventSource`, SSE libs, base URL, env vars). Do NOT edit the frontend.
- `docs/contract-mismatches.md`: table `frontend expects | backend has | resolution (backend change / frontend change needed / ok)`. Include: how it consumes chat streaming (POST-stream vs EventSource), event names/shape, upload field names, response shapes, error shape, approve payload, CORS/base URL.
- Fix mismatches on the backend side when additive/cheap (aliases, extra fields, extra route). List needed frontend changes for the frontend owner; don't guess.
- `tools/contract_check.py`: boots the app with stubs, hits every G11 endpoint, validates status + response fields via pydantic models; exit non-zero on failure. Add as pytest test.
- `docs/api-contract.md` (final contract, versioned `contract v1`) + `docs/openapi.json` export. Ask Soham to sign off with the frontend owner before calling it frozen.
**Done when** mismatch doc complete, contract_check green, api-contract.md matches actual behavior.
**PROMPT**
```
Do STEP 3 of build.prd.md (G4, G11 + `## STEP 3`). Frontend path: <FRONTEND_REPO_PATH>. Read frontend, never edit it. Produce docs/contract-mismatches.md, docs/api-contract.md, docs/openapi.json, tools/contract_check.py (+pytest). Fix backend-side mismatches only. Report ≤10 lines incl. required frontend changes.
```

## STEP 4 — Files, workspaces, path safety, knowledge & P&ID plumbing
Needs: G3 G6 G7 G8 G10 G11 G12 · Day 1–3
**Build**
- `core/workspace.py`: `create_workspace(task_id)`, `safe_join(root, user_path) -> Path`: reject empty, NUL bytes, absolute paths, `..` segments, drive letters, backslash tricks; resolve with `Path.resolve()` and require `resolved.is_relative_to(root.resolve())`; reject if any existing component is a symlink escaping root. Raises `PathRejectedError`. `cleanup_expired()` deletes only `scratch` of tasks older than WORKSPACE_TTL_HOURS (keep `outputs/`, audit).
- `core/files.py`: stream uploads to disk in 1 MB chunks, abort at MAX_UPLOAD_MB (413, delete partial), compute sha256, check extension whitelist + magic bytes (415), store under uuid name per G12, insert `files` row, audit FILE_UPLOADED. Never trust `Content-Type` or filename.
- `api/files.py`, `api/knowledge.py`: per G11. Knowledge upload sets `ingest_status=pending`, background task: `ingesting` → `rag.ingest(FileRecord)` → `ready` or `failed`(+error). Exceptions/malformed docs → `failed`, service stays up; audit INGEST_STARTED / INGEST_FAILED.
- `api/pid.py`: validate image (Pillow `verify()`, ext, MAX_PID_IMAGE_MB), save to `DATA_DIR/pid/{file_id}/`, create task `pid_analysis`, run `pid.extract_pid_graph` via `asyncio.to_thread` with `PID_TIMEOUT_S`, register graph JSON (`graph_json`) and overlay (`pid_overlay`) artifacts (Step 5 store; until then use interface), set task pid_graph + COMPLETE, audit. Timeout/exception → task FAILED + clean error.
**Done when** tests: `../../etc/passwd`, `/etc/passwd`, `a/../../b`, `C:\x`, NUL byte, symlink escape → all `PathRejectedError`; valid nested path ok; oversize upload → 413 with no leftover file; `.exe` renamed `.pdf` → 415; malformed doc via stub-raising ingestor → status failed, next request still works; P&ID happy path with stub; corrupted image → 4xx; PID timeout → FAILED.
**PROMPT**
```
Implement STEP 4 of build.prd.md (Needs G-sections + `## STEP 4`). Every model/user-derived path must use safe_join. Stream uploads, never load whole file in memory. Tests per "Done when". ruff+pytest green. Report ≤10 lines.
```

## STEP 5 — Artifact infrastructure + DOCX/XLSX generators
Needs: G3 G7 G8 G9 G10 G12 · Day 3
**Build**
- `core/artifacts.py` `ArtifactStoreImpl`: `register` (path must be inside task `outputs/` via safe_join; compute sha256; write `{artifact_id}.manifest.json` next to file with manifest fields; DB row; audit ARTIFACT_CREATED), `set_verification_status`, `get`, `verify_integrity` (re-hash vs stored), `package_code` (zip `code/` + any `outputs/test_results*.json` → `code_package`).
- `api/artifacts.py`: manifest JSON + `download_url`; `?download=1` → re-hash first; mismatch → 500 `ARTIFACT_CORRUPT` + audit ARTIFACT_CORRUPT. Missing file → 404 clean.
- `runtime/generators/docx.py` (python-docx). Input spec (validate with pydantic, reject unknown/oversize):
```json
{"title":"str","metadata":{"k":"v"},"sections":[{"heading":"str","paragraphs":["str"],"table":{"columns":["str"],"rows":[["str"]]},"citations":["chunk_id"]}],
 "evidence":[{"chunk_id":"str","document_id":"str","page":1,"section":"str","source_hash":"str"}],
 "calculations":[{"name":"str","formula":"str","inputs":{"k":"v"},"result":"str"}],"assumptions":["str"],"recommendation":"str"}
```
Output DOCX contains: title, metadata table, sections (citations rendered as `[chunk_id]`), evidence-reference table, calculation steps, assumptions, recommendation, an **Approval** block (Approved by / Date / Signature blank lines), footer with generation timestamp (UTC) and `content_hash` (sha256 of canonical spec JSON, sorted keys). File `artifact_hash` is in the manifest (G7).
- `runtime/generators/xlsx.py` (openpyxl): spec `{"sheets":[{"name","columns":[...],"rows":[[...]],"formulas":[{"cell":"B7","formula":"=SUM(B2:B6)"}]}]}`; sheet names ≤31 chars, no `[]:*?/\`; formulas must start with `=`, ≤ 200 chars; no external references (`[`, `http`) → reject.
**Done when** tests: register hashes correctly and manifest file matches DB; tampering with a file → download 500 ARTIFACT_CORRUPT + audit; path outside outputs rejected; generated DOCX re-opens with python-docx and contains every listed element; XLSX reopens with formulas intact; bad specs rejected before writing; `package_code` zip has expected files.
**PROMPT**
```
Implement STEP 5 of build.prd.md (Needs G-sections + `## STEP 5`). Follow the DOCX/XLSX specs exactly; no PPTX. Register via ArtifactStore only. Tests per "Done when". ruff+pytest green. Report ≤10 lines.
```

## STEP 6 — Tool runtime + Docker sandbox
Needs: G3 G6 G7 G8 G9 G12 · Day 2–4 (biggest step; if Docker missing, tests marked `docker` skip)
**Build**
- `sandbox/Dockerfile`: `python:3.11-slim`, install `pytest` only (image built while online; sandbox has no network at run time), non-root user uid 10001, `WORKDIR /work`, `ENV PYTHONDONTWRITEBYTECODE=1`. Build: `docker build -t indigent-sandbox:1 sandbox/`.
- `runtime/sandbox.py` (docker SDK in `asyncio.to_thread`): run container with: `network_mode="none"`, `read_only=True`, `tmpfs={"/tmp":"rw,noexec,nosuid,size=64m"}`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges"]`, `pids_limit=SANDBOX_PIDS`, `mem_limit=memswap_limit=SANDBOX_MEM_MB m`, `nano_cpus=SANDBOX_CPUS*1e9`, `user="10001:10001"`, ONE bind mount `{workspace}/code -> /work:rw`, `auto_remove=False` (remove in `finally`). Wait ≤ PER_TOOL_TIMEOUT_S then `kill()`. Read logs, cap each stream at SANDBOX_OUTPUT_LIMIT_KB (set `truncated`). `resource_events` values: `TIMEOUT`, `OOM_KILLED` (State.OOMKilled), `OUTPUT_TRUNCATED`, `PIDS_LIMIT` (stderr contains "can't start new thread" / "Resource temporarily unavailable"), `NETWORK_BLOCKED` (stderr contains "Network is unreachable" / "Name or service not known" / "Temporary failure in name resolution"). Audit SANDBOX_STARTED; on NETWORK_BLOCKED audit SANDBOX_BLOCKED_NETWORK. Docker unavailable/image missing → `SandboxUnavailableError` (no host fallback, ever).
- `sandbox/selftest.py` (run inside container): asserts outbound connect fails, rootfs not writable outside /work & /tmp, uid≠0, host paths (e.g. `/Users`, `/home/<host>`, docker socket) absent.
- `runtime/registry.py` tool impls (async `(ctx,args)->ToolResult`) + arg schemas (pydantic, `extra="forbid"`):
  - `read_file{path}` text only, ≤1 MB, within inputs/outputs/code.
  - `write_file{path,content}` under code/ or outputs/, ext `.py .txt .md .json .csv`, ≤1 MB.
  - `create_code{files:[{path,content}]}` ≤20 files, all under code/.
  - `execute_code{entrypoint:"main.py",args?:[str]}` args ≤10 strings ≤200 chars, no shell; runs `python -B <entrypoint> args…` in sandbox.
  - `run_tests{target?:"tests"}` runs `python -m pytest -q -p no:cacheprovider <target>`; result `data`: `{exit_code, passed, failed}` parsed from pytest summary.
  - `create_docx{output,spec}`, `create_xlsx{output,spec}` → Step 5 generators write into outputs/, then register artifact.
  - `ocr_document{path}`, `search_knowledge_base{query,top_k?}`, `retrieve_section{document_id,section}`, `analyze_image{path,prompt?}`, `extract_pid_graph{path}` → `services.ml_tools.call(...)` (Joy).
- `runtime/executor.py` `ToolRuntimeImpl.execute(ctx, decision)`: (1) require `decision.allowed` else raise; (2) tool must be in `ALLOWED_TOOLS[ctx.task_type]` else `ToolNotAllowedError` + audit POLICY_DENIED (component runtime) — defense in depth even if policy said yes; (3) re-run `safe_join` on path-like args (`path, output, entrypoint, files[].path, target`); (4) validate args with tool schema; (5) run with `asyncio.wait_for(PER_TOOL_TIMEOUT_S)`; (6) catch exceptions → `ToolResult(ok=False,error=…)` (no stack); (7) audit TOOL_EXECUTED (status ok|error|denied, details: tool, arg names/sizes, duration, resource_events). Never raise raw exceptions to the orchestrator except `ToolNotAllowedError`/`SandboxUnavailableError`.
**Done when** (docker-marked unless noted): selftest passes in container; code doing `socket.create_connection(("1.1.1.1",53))` fails and audit has SANDBOX_BLOCKED_NETWORK; `open("/etc/shadow")`/host path reads fail; infinite loop → TIMEOUT within ~PER_TOOL_TIMEOUT+3 s (use 3 s in test); memory bomb → OOM_KILLED; fork bomb → PIDS_LIMIT and host unaffected; 10 MB stdout → truncated to limit; `--network=none` verified via `docker inspect`; stopped Docker → SandboxUnavailableError (mock, no docker marker); unknown tool / tool not in task_type allow-list / `allowed=False` decision → rejected + audited (no docker); invalid args (extra field, `../x`) → rejected before execution (no docker); containers cleaned up after every run.
**PROMPT**
```
Implement STEP 6 of build.prd.md (Needs G-sections + `## STEP 6`). Sandbox flags in the spec are mandatory. Never run user/model code on the host; no fallback. Runtime must refuse to execute without an allowed PolicyDecision. Tests per "Done when" (docker-marked where noted). ruff+pytest green. Report ≤10 lines.
```

## STEP 7 — Models API, Sovereignty API, egress guard
Needs: G3 G6 G8 G9 G11 · Day 4
**Build**
- `api/models.py`: passthrough of `ModelsStatus.status()`; on exception → 503 with clean error (no fake data).
- `net/sovereignty.py` `SovereigntyImpl`: `record_external_call(provider, bytes_out, bytes_in)` (increments `external_api_calls` by 1 + bytes; audit not required, Joy audits PROVIDER_CALL), `snapshot()` builds G11 shapes from `settings.INFERENCE_MODE` + DB counters (never from network observation or model names). Integrity rule G7 (`AIR-GAP VIOLATED`). `api/monitoring.py` exposes it.
- `net/egress_guard.py` `install(mode)` at startup (defense layer 1, process level): wrap `socket.socket.connect`/`connect_ex` and `socket.getaddrinfo`. Local mode: allow only loopback (`127.0.0.0/8`, `::1`) plus hosts derived from `OLLAMA_BASE_URL`/`QDRANT_URL` if they are loopback/private; anything else → increment `denied_connections`, audit EGRESS_DENIED, raise `EgressDeniedError`. Groq mode: additionally allow only IPs returned by `getaddrinfo("api.groq.com")` (cache); on allowed non-local connect increment `external_connections`. Unix-socket and loopback traffic never counted. Document limits in code comment (process-only; other layers in Step 9).
**Done when** tests: local snapshot has `status=="AIR-GAPPED"`, all counters 0; groq snapshot never contains `AIR-GAPPED` (parametrized over many counter values); calling `record_external_call` 12× → `external_api_calls==12`; local mode `socket.create_connection(("93.184.216.34",80))` raises EgressDeniedError, `denied_connection_attempts` increments, audit EGRESS_DENIED exists, `external_*` stay 0; loopback connect allowed; local with counter forced >0 → `AIR-GAP VIOLATED`; mode not inferable (change model names → no effect); `/api/models` 503 path.
**PROMPT**
```
Implement STEP 7 of build.prd.md (Needs G-sections + `## STEP 7`). Mode comes only from settings. Groq mode must never yield AIR-GAPPED. Egress guard tests must not make real external connections (mock sockets/IPs). Tests per "Done when". ruff+pytest green. Report ≤10 lines.
```

## STEP 8 — Observability, health/readiness, cleanup, hardening pass
Needs: G3 G6 G11 · Day 4
**Build**
- `/healthz`, `/readyz` (G11): sqlite `SELECT 1`; docker `client.ping()`; sandbox image present; qdrant `GET {QDRANT_URL}/healthz`-style reachability; ollama `GET {OLLAMA_BASE_URL}/api/tags` (loopback only; short 2 s timeouts; report only).
- Uniform error handling audit: unhandled exception → 500 INTERNAL with request_id, stack only in logs. Request/task ids in every log line for a task's lifetime.
- Background loop: `cleanup_expired()` every hour. Graceful shutdown: cancel runners, mark running tasks FAILED `INTERRUPTED`, close DB.
- Body-size guard for JSON endpoints (reject > 1 MB, 413).
**Done when** tests: readyz reports each check; readyz 503 when docker mocked down; unhandled error → 500 format with no traceback in body; log lines for a chat task all carry the same task_id; shutdown marks running task FAILED.
**PROMPT**
```
Implement STEP 8 of build.prd.md (Needs G-sections + `## STEP 8`). Only add/adjust what the spec lists. ruff+pytest green. Report ≤10 lines.
```

## STEP 9 — Compose, deployment wiring, network lockdown docs
Needs: G3 G6 G7 · Day 4–5
**Build**
- `docker-compose.yml`: service `qdrant` only — pinned image tag (record the resolved tag/digest in `docs/decisions.md`), ports `127.0.0.1:6333:6333` (and 6334 if gRPC needed), volume `./data/qdrant:/qdrant/storage`, env `QDRANT__TELEMETRY_DISABLED=true`, restart `unless-stopped`.
- `Makefile` (or `scripts/`): `make setup` (venv+deps+build sandbox image), `make run`, `make test`, `make demo` (`INFERENCE_MODE=local` forced), `make groq-dev` (prints big warning; requires env GROQ_API_KEY).
- `docs/network-lockdown.md`: layered model (app guard → container policy → OS firewall → telemetry counters) with copy-paste steps to block outbound for the Python process/machine on macOS (pf), Windows (Windows Firewall outbound rule), Linux (iptables/nftables), and how to verify (attempt `curl https://example.com` → fails; sovereignty counters stay 0). State clearly which layers are automated vs manual. Also: pre-pull/build all images and models while online; then go offline for the demo.
- `.env.example` default `INFERENCE_MODE=local`. Add a test asserting the shipped `.env.example` and settings default are `local`.
**Done when** `docker compose up -d` brings Qdrant up bound to localhost only (verify `docker compose config`); readyz shows qdrant ok; docs exist; test for local default passes.
**PROMPT**
```
Do STEP 9 of build.prd.md (Needs G-sections + `## STEP 9`). Compose = Qdrant only (G7). Do not run destructive OS firewall commands; only document them. Report ≤10 lines incl. resolved image tag.
```

## STEP 10 — Integrate Joy's real modules + failure/security matrix (joint)
Needs: G2 G3 G7 G9 G11 · Day 5. Start only when Joy's modules are merged.
**Build**
- Flip `JOY_MODULES=real`; fix boundary breakages ONLY in your code; report Joy-side bugs to Soham (don't edit Joy dirs).
- Confirm with Joy: G7 `AIR-GAP VIOLATED` rule; Groq provider calls `record_external_call` per request; provider audits PROVIDER_CALL; orchestrator emits the G9 events; approval waits in orchestrator.
- `tests/integration/` matrix (run with real modules; mark `needs_models`). Each row: attack/failure → expected → test name:
  1. Local mode chat end-to-end (Demo A) · 2. Groq mode chat (sovereignty shows EXTERNAL INFERENCE ACTIVE, counter increments) · 3. Local provider down → task fails, **zero** Groq calls · 4. Missing local model → clean error · 5. Unauthorized tool → rejected + POLICY_DENIED audit · 6. `../../` and absolute path in tool args → rejected · 7. Sandbox network attempt → blocked + audit · 8. Sandbox host-file access → denied · 9. Malformed upload → ingest failed, service up · 10. Prompt injection in uploaded PDF → no tool authority gained · 11. False citation → VERIFY fails→REPAIR · 12. Bad calculation → validation fails · 13. Failed code test → repair loop; >3 repairs → task fails safely · 14. Runaway loop → hard timeout · 15. Tool timeout → audited · 16. Output flood → controlled failure · 17. Resource exhaustion → controlled failure · 18. Human approval flow (approve + reject) · 19. Artifact validation rejects invalid artifact · 20. Audit completeness: every category in G9 appears for the demo runs, all rows have inference_mode · 21. Sovereignty dashboard data correct in both modes · 22. Demo B and Demo C paths.
- `docs/demo-runbook.md`: exact commands, offline checklist, expected sovereignty output. Final: set/verify `INFERENCE_MODE=local` in shipped config and run the full matrix once in local mode.
**Done when** matrix green (or each failure filed with owner), runbook verified by running it from a clean clone.
**PROMPT**
```
Do STEP 10 of build.prd.md (Needs G-sections + `## STEP 10`). JOY_MODULES=real. Edit only Soham-owned code; list Joy-side bugs in the report. Implement tests/integration matrix rows 1-22 and docs/demo-runbook.md. Report ≤10 lines + failing rows with owner.
```

---

## APPENDIX A — Prompt-token discipline (for the human)
- One step per fresh session; the step prompt + AGENTS.md is all it needs.
- If the agent asks something the doc answers, reply with the section id only (e.g. "G7").
- After a step passes, commit; next session starts clean (agent re-reads only its sections).

## APPENDIX B — Global definition of done
`ruff check .` clean · `pytest -q` green (docker tests skip without Docker) · no secrets in repo/logs · no imports of LLM SDKs · no edits in Joy dirs · `docs/decisions.md` updated · contract unchanged unless Soham+Joy agreed.
