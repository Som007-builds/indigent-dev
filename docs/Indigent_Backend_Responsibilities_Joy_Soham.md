# Indigent Backend Responsibilities

## Backend & ML Engineer — Joy

### Primary Ownership
Joy owns the AI control plane, ML integration, model execution layer, and the security/verification logic surrounding agent execution.

### Responsibilities

- **Inference Provider Layer**
  - Implement the `InferenceProvider` interface.
  - Implement `OllamaProvider` for local inference.
  - Implement `GroqProvider` for sanctioned development/testing.
  - Enforce explicit `INFERENCE_MODE=local|groq`.
  - Ensure no direct Ollama/Groq SDK usage outside `providers/`.

- **Model Registry & Router**
  - Maintain the model capability registry.
  - Implement task → capability → hardware → mode → model selection.
  - Handle local hardware profiles for Apple Silicon and RTX 3050A.
  - Fail cleanly when the selected model is unavailable.
  - Never silently fall back between inference modes.

- **Resource Manager**
  - Manage model loading/residency and unloading.
  - Track VRAM/RAM availability and model resource requirements.
  - Handle concurrency and resource-aware model selection.

- **Agent Orchestrator**
  - Implement the bounded state machine:
    `INTAKE → CLASSIFY → PLAN → RETRIEVE → TOOL → VERIFY → REPAIR → ARTIFACT → ARTIFACT_VALIDATE → APPROVAL → COMPLETE`
  - Implement genuinely dynamic model-generated planning.
  - Implement bounded retries, timeouts, and task limits.
  - Implement verification and repair loops.

- **Policy Validation Layer**
  - Validate every model-generated tool request before execution.
  - Enforce tool/task authorization.
  - Validate tool arguments, paths, workspace boundaries, file types/sizes, and resource limits.
  - Ensure LLM output never directly authorizes an action.

- **RAG & Evidence Pipeline**
  - Own parsing/OCR orchestration, chunking, embeddings, retrieval, and reranking.
  - Integrate Qdrant at the ML/RAG interface level.
  - Maintain evidence provenance from document → chunk → claim.
  - Implement citation-consistency verification.
  - Trigger repair when evidence verification fails.

- **Multimodal / P&ID ML Integration**
  - Integrate local VLM capability.
  - Own the ML-facing P&ID pipeline interface.
  - Integrate P&ID graph extraction and confidence outputs.
  - Handle multimodal verification requirements.

- **Coding Model & Verification**
  - Integrate the coding model.
  - Drive the code execution/test/repair loop.
  - Validate generated code results before completion.

- **Artifact Validation**
  - Define and implement semantic validation of generated artifacts.
  - Verify claims, calculations, citations, and required fields.
  - Generate/maintain evidence and artifact manifests where applicable.

- **Sovereignty / ML Integration**
  - Integrate inference mode and provider state with the Sovereignty Monitor.
  - Ensure local mode is never falsely reported as external or vice versa.
  - Expose inference-call information required by monitoring/audit systems.

- **ML/Control-Plane Security Testing**
  - Test prompt injection.
  - Test RAG poisoning and malicious documents.
  - Test unauthorized tool selection.
  - Test malformed tool arguments.
  - Test false citations.
  - Test runaway agent loops.
  - Test model/resource exhaustion.
  - Test local-model failure and forbidden Groq fallback.

---

# Backend Engineer — Soham

### Primary Ownership
Soham owns the platform backend, API layer, persistence, execution infrastructure, file/artifact lifecycle, and frontend/backend integration.

### Responsibilities

- **FastAPI API Gateway**
  - Implement and maintain backend API endpoints.
  - Implement request/response schemas and validation.
  - Reconcile the API contract with the React frontend.
  - Freeze the contract after reconciliation.

- **Task Management & Persistence**
  - Implement SQLite task-state persistence.
  - Store task metadata, state transitions, errors, and final results.
  - Implement task retrieval and recovery mechanisms.
  - Implement:
    - `GET /api/tasks/{task_id}`
    - `GET /api/tasks/{task_id}/timeline`

- **SSE / Progress Streaming**
  - Implement `/api/chat` task creation and SSE progress streaming.
  - Serialize state transitions, tool events, verification events, errors, and completion events.
  - Maintain the agreed frontend SSE event schema.

- **File Management**
  - Implement file upload/download handling.
  - Create and manage per-task workspaces.
  - Store file metadata.
  - Enforce workspace lifecycle and cleanup.
  - Implement:
    - `POST /api/files/upload`

- **Artifact Infrastructure**
  - Manage artifact storage and retrieval.
  - Implement artifact metadata and lifecycle.
  - Implement:
    - `GET /api/artifacts/{artifact_id}`
  - Provide the infrastructure required by Joy's artifact validation layer.

- **Audit Infrastructure**
  - Implement SQLite audit-log persistence.
  - Store task events, tool calls, verification events, errors, and inference mode.
  - Implement audit timeline retrieval.

- **Tool Runtime Infrastructure**
  - Provide the execution plumbing for registered tools.
  - Handle process/container lifecycle.
  - Capture stdout/stderr and structured tool results.
  - Integrate tool execution with the Policy Validation Layer.

- **Sandbox Infrastructure**
  - Implement Docker/process sandbox lifecycle.
  - Enforce filesystem/workspace mounts.
  - Enforce network isolation.
  - Enforce execution timeouts and resource limits.
  - Ensure sandbox execution remains isolated in both local and Groq modes.

- **Knowledge/File Ingestion Plumbing**
  - Implement the backend side of:
    - `POST /api/knowledge/upload`
  - Receive and persist uploaded documents.
  - Hand documents to Joy's RAG/ML ingestion pipeline.
  - Track ingestion status.

- **P&ID API Integration**
  - Implement:
    - `POST /api/pid/analyze`
  - Handle image upload/request validation.
  - Connect the endpoint to Joy's P&ID interface.
  - Return structured P&ID results.

- **Model/Monitoring APIs**
  - Implement:
    - `GET /api/models`
    - `GET /api/monitoring/sovereignty`
  - Expose the data supplied by the model/resource and sovereignty subsystems.

- **Configuration & Deployment**
  - Maintain backend configuration and environment handling.
  - Manage Docker Compose/startup wiring for backend services.
  - Integrate SQLite, Qdrant, Ollama, sandbox infrastructure, and supporting services.
  - Ensure secrets are handled through environment configuration.

- **Observability & Error Handling**
  - Implement structured backend logging.
  - Maintain request/task IDs across services.
  - Provide consistent API error responses.
  - Implement health/readiness checks where required.

- **Backend/Infrastructure Testing**
  - Test malformed requests and uploads.
  - Test path traversal and unsafe file handling.
  - Test sandbox escape attempts.
  - Test network isolation.
  - Test artifact corruption and retrieval failures.
  - Test task persistence/recovery.
  - Test SSE failures and frontend integration.
  - Test API-level resource and timeout enforcement.

---

## Responsibility Boundary

### Joy owns the decisions and intelligence

- Which model runs.
- Why that model is selected.
- What the agent should do next.
- Which tools the agent is allowed to use.
- Whether model-generated tool arguments are safe.
- What evidence supports a claim.
- Whether verification passes.
- Whether an agent should repair its output.
- Whether an artifact is semantically valid.
- ML/model/RAG/P&ID behavior.

### Soham owns the platform and execution mechanisms

- How requests enter the backend.
- How tasks are persisted.
- How progress reaches the frontend.
- How files and workspaces are managed.
- How tools are physically executed.
- How the sandbox is created and isolated.
- How artifacts are stored and retrieved.
- How audit events are persisted.
- How services are wired, deployed, logged, and exposed through APIs.

### Shared Integration

Both engineers jointly own:

- End-to-end integration.
- API contract reconciliation.
- Security testing.
- Demo-path reliability.
- Performance benchmarking.
- Final 5-day integration and stabilization.
- Fixing issues that cross the AI-control-plane/platform boundary.

## Core Principle

**Joy:** decides what the AI is allowed to do and verifies what it did.

**Soham:** provides the platform that safely executes, stores, exposes, and records it.
