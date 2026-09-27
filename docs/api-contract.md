# Indigent — API Contract v1

> Status: **frozen** (contract v1). Changes require sign-off from Soham + frontend owner.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and tested |
| ⬜ | Spec'd; not yet implemented |

---

## Base URL

`http://127.0.0.1:8000` (backend binds loopback only — G3.8)

---

## Common Headers

Every response carries:

| Header | Value |
|--------|-------|
| `X-Request-ID` | UUID, generated if not supplied by client |
| `X-Inference-Mode` | `local` or `groq` |

---

## Error Envelope

All 4xx/5xx responses use:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Task not found",
    "request_id": "...",
    "task_id": "..."
  }
}
```

`task_id` is only present when the error is task-scoped.

---

## Endpoints

### `GET /healthz` ✅

**Purpose**: Liveness probe — returns immediately without checking dependencies.

**Response 200**
```json
{ "ok": true }
```

---

### `GET /readyz` ✅

**Purpose**: Readiness probe — checks each dependency.

**Response 200 / 503** (503 when sqlite, docker, or sandbox_image fail)
```json
{
  "sqlite": "ok",
  "docker": "ok",
  "sandbox_image": "ok",
  "qdrant": "ok",
  "ollama": "ok"
}
```

Each value is `"ok"` or `"fail"`. `qdrant` and `ollama` are informational only
(their failure does not trigger 503).

---

### `POST /api/chat` ✅

**Purpose**: Submit a user request; returns an SSE stream of task events.

**Request body**
```json
{
  "message": "str (1..MAX_MESSAGE_CHARS=20000)",
  "file_ids": ["optional", "list", "of", "file_ids"],
  "knowledge_ids": ["optional", "list"]
}
```

**Response**: `text/event-stream` — SSE, first event is `task_created`.

**Response header**: `X-Task-Id: <task_id>`

**Client disconnect behaviour**: disconnect does NOT cancel the task. The runner
continues until the task reaches a terminal state (`completed` or `failed`).

**Error codes**:
- `422` — message empty or exceeds `MAX_MESSAGE_CHARS`
- `429` — active tasks ≥ `MAX_ACTIVE_TASKS=2`

---

### `GET /api/tasks/{id}/stream` ✅

**Purpose**: Join an existing task's SSE stream (or replay a finished task).

Supports `Last-Event-ID` header: replays events with `seq > last_event_id`,
then switches to live delivery. No gaps, no duplicates.

**Response**: same SSE format as `/api/chat`.

---

### `GET /api/tasks/{id}` ✅

**Purpose**: Fetch current task state.

**Response 200**
```json
{
  "task_id": "uuid",
  "user_request": "...",
  "task_type": "inspection | coding | pid_analysis | null",
  "plan": [...],
  "current_state": "INTAKE | CLASSIFY | ... | COMPLETE | FAILED",
  "inference_mode": "local | groq",
  "model_used": "string | null",
  "tool_calls": [...],
  "retrieved_chunks": [...],
  "artifacts": [{ "artifact_id": "...", "artifact_type": "...", "path": "...", ... }],
  "pid_graph": null,
  "errors": [...],
  "verification_status": "pending | passed | failed",
  "final_result": null,
  "requires_human_approval": 1,
  "approved_by": null,
  "created_at": "2026-09-25T10:00:00Z",
  "updated_at": "2026-09-25T10:00:00Z"
}
```

---

### `GET /api/tasks/{id}/timeline` ✅

**Purpose**: Fetch audit log entries for a task (ordered by `id`).

**Response 200**
```json
{
  "task_id": "uuid",
  "entries": [
    { "id": 1, "ts": "...", "category": "TASK_CREATED", "component": "runner", "action": "task_created", "status": "ok", "details": {} }
  ]
}
```

---

### `POST /api/tasks/{id}/approve` ✅

**Purpose**: Approve or reject a task that is waiting in `APPROVAL` state.

**Request body**
```json
{
  "approver": "Engineer Name",
  "decision": "approve | reject",
  "note": "optional free text"
}
```

**Response 200** — returns the task state *as-of the approval call*:
```json
{
  "task_id": "uuid",
  "current_state": "APPROVAL",
  "approved_by": "Engineer Name"
}
```

> **Design note**: `current_state` in the response reflects the state
> **at the time the approve request was processed**, which is `APPROVAL`
> (or `FAILED` if the orchestrator immediately rejected it). The task
> continues running in the background; use `GET /api/tasks/{id}` or
> `GET /api/tasks/{id}/stream` to observe the subsequent state transitions
> to `COMPLETE` or `FAILED`. This fire-and-continue behaviour prevents HTTP
> clients from blocking indefinitely on a long post-approval execution phase.

**Error codes**:
- `404` — task not found
- `409` — task is not in `APPROVAL` state, or approval was already submitted

---

### `POST /api/files/upload` ✅

**Purpose**: Upload one or more files attached to a task.

**Request**: `multipart/form-data`, field `file` (repeated), optional `task_id`.

**Response 200**
```json
{
  "files": [
    { "file_id": "uuid", "name": "filename.pdf", "size": 1024, "sha256": "...", "mime": "application/pdf", "kind": "upload" }
  ]
}
```

Allowed extensions: `.pdf .png .jpg .jpeg .tif .tiff .docx .xlsx .pptx .txt .md .csv .json`.  
Magic bytes are verified (not just extension).  
Files exceeding `MAX_UPLOAD_MB=50` → `413`.  
Unknown extension or magic mismatch → `415`.

---

### `POST /api/knowledge/upload` ✅

**Purpose**: Upload knowledge-base documents (triggers background RAG ingestion).

**Request**: `multipart/form-data`, field `file` (repeated).

**Response 200**
```json
{
  "files": [
    { "file_id": "uuid", "name": "doc.pdf", "size": 1024, "sha256": "...", "mime": "application/pdf", "ingest_status": "pending" }
  ]
}
```

Ingestion runs in the background. Poll `GET /api/knowledge/{file_id}` for status.

---

### `GET /api/knowledge/{file_id}` ✅

**Purpose**: Check ingestion status of a knowledge file.

**Response 200**
```json
{
  "file_id": "uuid",
  "name": "doc.pdf",
  "ingest_status": "pending | ingesting | ready | failed",
  "ingest_error": null
}
```

---

### `GET /api/artifacts/{id}` ✅

**Purpose**: Fetch artifact manifest, optionally download the file.

**Response 200 (manifest)**
```json
{
  "artifact_id": "uuid",
  "task_id": "uuid",
  "artifact_type": "docx | xlsx | graph_json | code_package | pid_overlay",
  "path": "...",
  "created_at": "2026-09-25T10:00:00Z",
  "artifact_hash": "sha256hex",
  "source_evidence_ids": [],
  "verification_status": "pending | passed | failed",
  "metadata": {},
  "download_url": "/api/artifacts/{id}?download=1"
}
```

**`?download=1`**: re-hashes the file; if hash mismatches → `500 ARTIFACT_CORRUPT` + audit entry.

---

### `GET /api/models` ✅

**Purpose**: Passthrough to Joy's `ModelsStatus.status()`.

**Response 200**
```json
{
  "active_inference_mode": "local",
  "hardware_profile": "mac_silicon",
  "models": [...],
  "resident_models": [],
  "resources": { "vram_mb_free": 0, "ram_mb_free": 0, "disk_mb_free": 0, "max_concurrency": 1 }
}
```

---

### `GET /api/monitoring/sovereignty` ✅

**Purpose**: Sovereignty monitor — proves data never left the device.

**Local mode response 200**
```json
{
  "inference_mode": "local",
  "status": "AIR-GAPPED",
  "provider": "ollama",
  "network_policy": "deny_all",
  "internet_access": "BLOCKED",
  "sandbox_network": "disabled",
  "external_api_calls": 0,
  "external_connections": 0,
  "external_bytes_out": 0,
  "external_bytes_in": 0,
  "denied_connection_attempts": 0,
  "since": "2026-09-25T10:00:00Z"
}
```

> **G3 invariant**: if `inference_mode=local` and any external counter > 0,
> `status` must be `"AIR-GAP VIOLATED"` (never `"AIR-GAPPED"`).

**Groq mode response**: `status: "EXTERNAL INFERENCE ACTIVE"`, `provider: "Groq"`.

---

### `POST /api/pid/analyze` ✅

**Purpose**: Run P&ID analysis on an uploaded image.

**Request**: `multipart/form-data`, field `file` (PNG/JPEG/TIFF, max `MAX_PID_IMAGE_MB=25`).

**Response 200**
```json
{
  "task_id": "uuid",
  "graph": {
    "nodes": [...],
    "edges": [...],
    "narrative": "...",
    "confidence_summary": {},
    "overlay_artifact_id": "uuid"
  },
  "artifact_ids": ["uuid", "uuid"]
}
```

---

## SSE Event Reference

All events follow the envelope:

```json
{
  "id": 42,
  "task_id": "uuid",
  "ts": "2026-09-25T10:00:00Z",
  "type": "state_changed",
  "inference_mode": "local",
  "data": { ... }
}
```

Terminal events (`completed`, `failed`) close the stream.

| Event type | Emitted by |
|------------|-----------|
| `task_created` | runner |
| `state_changed` | orchestrator |
| `message` | orchestrator |
| `plan` | orchestrator |
| `model_selected` | orchestrator |
| `tool_proposed` | orchestrator |
| `policy_decision` | orchestrator |
| `tool_result` | orchestrator |
| `retrieval` | orchestrator |
| `verification` | orchestrator |
| `repair` | orchestrator |
| `artifact_created` | orchestrator |
| `artifact_validation` | orchestrator |
| `pid_graph` | orchestrator |
| `approval_requested` | orchestrator |
| `approved` / `rejected` | runner |
| `completed` | orchestrator |
| `failed` | orchestrator / runner |

---

*Last reviewed: 2026-09-26. Contract owner: Soham. Sign-off required from frontend owner before publishing.*
