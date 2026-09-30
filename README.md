# Indigent

### Sovereign Agentic AI Workbench

**Private AI. Autonomous Workflows. Verifiable Sovereignty.**

Indigent is a local-first, agentic AI workbench for organizations that work with confidential industrial information — refineries, public-sector undertakings (PSUs), defence-linked manufacturing, and engineering enterprises — where documents such as P&IDs, inspection reports, vendor terms, financial records, and proprietary designs must never leave the building.

Built for **Smart India Hackathon 2026 · Problem Statement 26117** — *Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work* · Team **Codecels**.

Most AI products assume the data can travel to a cloud service. Indigent takes the opposite position: the model, the knowledge base, the execution environment, the audit trail, and the generated deliverables all live on one local machine. Model output is treated as an *untrusted proposal* — it can propose actions, but nothing runs until it has passed a deterministic policy validator and, where consequential, a human approval gate.

Indigent is not a chat wrapper around a local LLM. It is a control plane that coordinates multi-step work: classify the request, plan, retrieve from an internal knowledge base, execute only approved tools inside a network-isolated sandbox, verify results, generate real deliverables (DOCX, XLSX, code packages, P&ID graphs), and record every step in an append-only audit log. A live **Sovereignty Monitor** reports exactly how much of this activity touched anything outside the machine.

| Attribute | Details |
|---|---|
| Project | Indigent |
| Category | Sovereign Agentic AI Workbench |
| Domain | Agentic AI / Industrial Automation / Data Sovereignty |
| Deployment model | On-premise, single machine (frontend → backend → local models) |
| Primary interface | Local web UI (workspace, documents, knowledge, models, audit) |
| Backend | Python 3.11+ · FastAPI · SQLite (WAL) · Server-Sent Events |
| Frontend | Next.js 16 (App Router) · React 19 · Tailwind CSS v4 |
| AI inference | Local open-weight models via Ollama (loopback); Groq is an opt-in dev/test path only |
| Vector storage | Qdrant (loopback, Docker Compose) |
| Sandboxing | Docker, `--network=none`, read-only filesystem |
| License | Not yet specified — check the repository for licensing information |

---

## 🎥 Demo Video

[![Watch the Indigent Demo](https://img.shields.io/badge/Watch-Demo%20Video-red?style=for-the-badge&logo=youtube)](DEMO_VIDEO_URL_HERE)

> Demo video coming soon. Replace `DEMO_VIDEO_URL_HERE` with the official YouTube or other public demonstration URL once available.

The planned demo follows the runbook in [`docs/demo-runbook.md`](docs/demo-runbook.md): launch the workbench, upload a sample inspection document, watch the agent classify, plan, retrieve from the local knowledge base, execute approved tools, and produce a verified deliverable — with the Sovereignty Monitor showing zero external calls throughout. See [Expected Demonstration Workflow](#expected-demonstration-workflow).

---

## Table of Contents

- [The Problem](#the-problem)
- [The Indigent Approach](#the-indigent-approach)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Repository Layout](#repository-layout)
- [Use Cases](#use-cases)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Model Support](#model-support)
- [Hardware and System Requirements](#hardware-and-system-requirements)
- [Security Architecture](#security-architecture)
- [Data Privacy and Sovereignty](#data-privacy-and-sovereignty)
- [Expected Demonstration Workflow](#expected-demonstration-workflow)
- [Screenshots and Visuals](#screenshots-and-visuals)
- [API Reference](#api-reference)
- [Testing and Validation](#testing-and-validation)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements and References](#acknowledgements-and-references)
- [Team and Project Information](#team-and-project-information)
- [Disclaimer](#disclaimer)

---

## The Problem

Industrial organizations constantly handle information that is confidential by nature: piping and instrumentation diagrams (P&IDs), engineering drawings, inspection reports, internal SOPs, financial records, vendor negotiations, procurement terms, and proprietary designs. Uploading any of it to a public or cloud-hosted AI assistant is a data-exfiltration risk that most such organizations simply cannot accept — contractually, legally, or technically.

The practical consequence is that these teams continue to do by hand what modern AI could accelerate: reading reports, cross-referencing standards and SOPs, drafting approval notes, running engineering calculations, and maintaining institutional knowledge spread across disconnected files. Data rarely leaves the building, but neither does the productivity gain.

The risks are not theoretical:

- Employees using unauthorized external AI tools on confidential documents create an unknowable, unmanaged exposure.
- Cloud inference of restricted designs, financial terms, or vendor strategies can violate confidentiality obligations or procurement rules.
- Government-linked and defence-adjacent organizations face explicit restrictions on where data may be processed.

For refineries, PSUs, and defence-linked manufacturing, the requirement is not "keep the data mostly local" — it is *demonstrable control*: the ability to show that model inference, document processing, retrieval, and execution all happen inside the organization's own infrastructure, with no silent fallback to the cloud.

## The Indigent Approach

Indigent addresses the problem with four design principles:

> **Local intelligence. Controlled autonomy. Verifiable execution. Complete data sovereignty.**

- **Locally controlled inference.** Open-weight language and vision models run through Ollama on the local machine. `INFERENCE_MODE=local` is the shipped and demo configuration; there is no automatic fallback to any cloud provider. Groq exists only as an explicitly configured development/testing path, and the UI and Sovereignty Monitor never present that mode as air-gapped.
- **Multi-model orchestration, not a single chat answer.** A model registry, a hardware-profile-aware router, and a task classifier turn a request into a typed task (`inspection`, `coding`, or `pid_analysis`) that is matched against the models and tools actually available.
- **Multi-step agentic workflows.** The agent runs through a bounded state machine — intake, classify, plan, retrieve, tool, verify, repair, artifact, validate, approve, complete — rather than a single prompt-response round trip.
- **Controlled tool use.** Every tool call is proposed by the model but authorized only by a deterministic policy validator against a per-task-type allow-list. Model output never authorizes an action.
- **Internal knowledge retrieval.** Documents uploaded to the knowledge base are chunked, embedded by a local embedding model, and stored in a local Qdrant vector store. Retrieval is document-scoped and evidence carries provenance so answers can be traced to their source.
- **Real deliverables.** The system generates practical outputs — Word documents, Excel workbooks, code packages, P&ID graph JSON — with SHA-256 integrity hashing and a verification pass before they are presented.
- **Human oversight.** Consequential deliverables wait in an explicit `APPROVAL` state for a named approver before the task can complete.
- **Auditability.** Every task emits a typed event stream and maps to an append-only audit log; a Sovereignty Monitor tracks external-call counters and network policy live.

The distinction from a chat interface is deliberate: a chatbot responds to messages; Indigent is designed to coordinate tasks, use approved tools, retrieve organizational knowledge, process documents, produce deliverables, and maintain execution traceability. Where a capability is not yet fully operational, this document says so explicitly — see [Roadmap](#roadmap).

## Key Features

### 1. Intelligent Model Routing

**Problem:** different kinds of work need different models, and a constrained machine cannot hold every model at once.

**Implementation:** A `ModelInventoryRecord` config (`MODEL_INVENTORY_JSON`) declares each model's provider, inference mode, task capabilities, hardware profiles, and memory estimate. At runtime the `ModelRouter` filters candidates by task type, configured mode, hardware profile, residency, and a `ResourceManager` admission check, then health-checks the provider before selecting. The router reads `INFERENCE_MODE` itself and fails closed if no compatible model is available (`ModelUnavailableError`), rather than silently picking a fallback.

**Status:** Implemented in the real control plane. Model *availability* is separate from *automatic routing*: `GET /api/models` reports what is actually resident and healthy, the router selects among available candidates, and `POST /api/models/active` records an explicit operator selection. The stub build (default) honestly reports an empty registry and no resident models.

### 2. Agentic Planning and Execution

**Problem:** a useful answer for industrial work usually requires several steps, and those steps must be safe, bounded, and observable.

**Implementation:** Tasks pass through a typed state machine (`INTAKE → CLASSIFY → PLAN → RETRIEVE → TOOL → VERIFY → REPAIR → ARTIFACT → ARTIFACT_VALIDATE → APPROVAL → COMPLETE`), with hard timeouts at every level (tool, model generation, and overall task), a bounded repair loop (at most 3 attempts), and a detached background runner that survives client disconnects. Every transition is streamed as an SSE event and persisted.

**Status:** The runner, event bus, persistence, state machine, and timeouts are implemented and tested. The planner/classifier prompts are implemented in the real control plane and exercised by live tests against local models; the default stub orchestrator walks the same event contract for development.

### 3. Multimodal Document Intelligence

**Problem:** industrial documents are often scanned, hand-annotated, or drawn (P&IDs, inspection photos, technical drawings).

**Implementation:** The file intake tier supports `.pdf .png .jpg .jpeg .tif .tiff .docx .xlsx .pptx .txt .md .csv .json`, verifies magic bytes (not just extensions), and streams uploads safely. A local OCR adapter is wired into the RAG extraction pipeline (with a mock adapter for hermetic tests; Tesseract-based OCR is environment-dependent). P&ID analysis is modeled as a structured `PIDGraph` (nodes, edges, overlay reference, narrative, confidence summary) with image-capability-aware routing so image-only work fails closed when no vision-capable model is available.

**Status:** File intake, OCR adapter wiring, the `PIDGraph` contract, and the `/api/pid/analyze` route are implemented and tested. The full vision transport to a local multimodal model and the production P&ID graph extraction are Joy-controlled internals that are currently stubbed in this checkout (the stub honestly returns an empty graph) — see [Roadmap](#roadmap).

### 4. Local Knowledge Base and Retrieval-Augmented Generation

**Problem:** answers should come from the organization's own documents, with provenance, not from the model's general knowledge.

**Implementation:** `POST /api/knowledge/upload` ingests documents in the background: extraction (PDF via PyMuPDF), deterministic chunking with stable chunk IDs and source hashing, embeddings from a locally provisioned Ollama embedding model (validated against `GET /api/tags` — a missing model is never pulled), and storage in a local Qdrant collection. Retrieval supports document-scoped filtering and expanded candidate recall, returning evidence items with document ID, chunk ID, page/section, source hash, and scores. Citation verification checks each claim in a generated answer against the retrieved evidence before the answer is surfaced.

**Status:** Production ingestion, retrieval, embeddings, Qdrant storage, and citation verification are implemented and validated in live tests (document-scoped retrieval and grounded answers were validated against a real ingested document with `qwen3.8-27b-abliterated:latest` for generation and `embeddinggemma:latest` for embeddings).

### 5. Industrial Workflow Automation

**Problem:** inspection reports, SOP reviews, and approval notes consume significant manual effort and require traceability.

**Implementation:** The bounded agent coordinate loop — classify → plan → retrieve → execute tools → verify → generate artifact → approve — is the mechanism for these workflows. Generated deliverables are grounded in retrieved evidence, and executions are recorded in the audit timeline.

**Status:** The framework and the tool set (read/write file, create/execute/run-tests code, DOCX/XLSX generators, OCR, knowledge search and retrieval — see the allow-list in [Repository Layout](#repository-layout)) are implemented. End-to-end acceptance of every industrial scenario is still in progress; see [Use Cases](#use-cases) for which paths are operational today vs. proposed.

### 6. Deliverable Generation

**Problem:** output must be a usable engineering document or package, not just text.

**Implementation:** `create_docx` and `create_xlsx` generators produce real `.docx` reports and `.xlsx` workbooks from bounded generator specs (1 MiB spec cap, 200-section cap). Code is packaged into a `code_package.zip` artifact containing the code and test results. Every artifact is registered with a manifest (type, path, source-evidence IDs, SHA-256 hash, verification status), and downloads re-hash the file and refuse to serve tampered artifacts.

**Status:** Implemented and tested. DOCX/XLSX generation, artifact registration, integrity verification, and tamper detection are covered by the test suite; PPTX generation is deliberately not built (no such tool exists in the allow-list).

### 7. Secure Code Execution

**Problem:** generated code must run — but never with host privileges or network access.

**Implementation:** Executable code runs only inside the `indigent-sandbox:1` Docker image built from `sandbox/Dockerfile` (Python 3.11-slim, non-root user, no shell). Containers are created with `network_mode="none"`, a read-only root filesystem, a `noexec` tmpfs for `/tmp`, all capabilities dropped, `no-new-privileges`, PID/memory/CPU limits, and a 64 KB per-stream output cap. Only the task's `code/` directory is mounted (at `/work`). If Docker or the image is unavailable, tool execution fails loudly with `SANDBOX_UNAVAILABLE` — there is **no host-subprocess fallback**.

**Status:** Implemented and tested, including network-isolation and resource-limit assertions. See [Security Considerations and Limitations](#security-considerations-and-limitations) for the residual risks.

### 8. Policy Validation and Human Oversight

**Problem:** the model must propose, but never authorize.

**Implementation:** Every tool proposal is a `ToolRequest` that must be validated by the policy layer into a `PolicyDecision(allowed=True)` before the runtime will execute it. The runtime *re-checks* both the decision and the per-task-type allow-list, and refuses anything else. Sensitive task outcomes require an explicit human approval: the task parks in `APPROVAL` until `POST /api/tasks/{id}/approve` is called with an approver name and a decision.

**Status:** Implemented and tested. The policy validator (allow-list, argument schemas, path-traversal rejection) is covered by `tests/test_policy.py` and friends. Authentication and role-based access control are out of scope for the current version (no-auth is a recorded decision).

### 9. Data Sovereignty and Network Observability

**Problem:** "air-gapped" must be proven, not asserted.

**Implementation:** The backend binds `127.0.0.1` only. In `local` mode a process-wide egress guard denies socket connections to anything except the configured loopback services (Ollama, Qdrant), and every denied attempt is counted and audited. The sandbox network interface is disabled. Sovereignty counters (external calls, connections, bytes in/out, denied attempts) are persisted in SQLite and surfaced live at `GET /api/monitoring/sovereignty`; if the mode is `local` and any external counter is non-zero, the status reports **`AIR-GAP VIOLATED`** — never `AIR-GAPPED`. Every HTTP response carries an `X-Inference-Mode` header so the UI can never guess.

**Status:** Implemented and tested. What this guarantees vs. what remains deployment-dependent is documented in [Data Privacy and Sovereignty](#data-privacy-and-sovereignty).

## Architecture

The system is a single-machine, three-process stack: a Next.js frontend, the FastAPI backend on the host, and Docker/Qdrant/Ollama as local infrastructure. The browser talks only to the frontend; the frontend proxies `/api/*` to the backend server-side (see the route handler in `frontend/ai-harness-sih-main/app/api/[...path]/route.ts`), so the backend's address never enters a client bundle.

```mermaid
flowchart TD
    U[User - local browser] -->|same-origin /api/*| F[Next.js frontend :3000]
    F -->|server-side proxy| B[FastAPI backend 127.0.0.1:8000]

    subgraph Backend
        B --> TR[TaskRunner - detached, state machine]
        TR --> OR[Agent Orchestrator]
        OR --> CL[Classify: inspection | coding | pid_analysis]
        OR --> PL[Planner]
        OR --> RT[Model Router + Resource Manager]
        RT --> PV["Providers (Ollama loopback; Groq opt-in)"]
        OR --> POL[Policy Validator - allow-list, schemas]
        POL -->|PolicyDecision allowed=True| RUN[Tool Runtime]
        RUN --> SB["Docker sandbox - network=none, read-only"]
        RUN --> RG[DOCX / XLSX generators]
        OR --> RAG[Local knowledge - Qdrant + Ollama embeddings]
        OR --> AV[Artifact validation + approval gate]
    end

    SB -->|code/ mounted only| WORK[Task workspace]
    B --> DB[(SQLite - tasks, audit, files, artifacts)]
    B --> SM[Sovereignty Monitor - egress guard + counters]

    PV -->|local models| OLL[Ollama 127.0.0.1:11434]
    RAG --> QD[Qdrant 127.0.0.1:6333]
```

**Data flow:** a user submits a request (with optional uploaded files or knowledge IDs). The runner creates a task, copies inputs into `DATA_DIR/workspaces/{task_id}/{inputs,outputs,code}/`, and streams SSE events as the orchestrator classifies the task, plans steps, selects a model through the router, proposes tools, and executes them only after policy validation. Retrieval pulls evidence from the local Qdrant index; generated artifacts are registered with hashes and manifests; consequential deliverables await human approval; every event maps to an append-only audit row. The Sovereignty Monitor continuously reports external-call counters and network policy.

Key security boundaries implemented in code:

- `app/runtime/executor.py` — the tool runtime independently re-checks the policy decision **and** the allow-list. Model output proposes; it never authorizes.
- `app/runtime/sandbox.py` — `network_mode="none"` and the read-only, capability-dropped container config.
- `app/net/egress_guard.py` — process-wide socket-level egress guard installed once at startup.
- `app/core/audit.py` + SQLite triggers — append-only audit log.
- `app/net/sovereignty.py` — sovereignty snapshot that can never claim `AIR-GAPPED` when an external counter is non-zero.

See [`Indigent-visuals/indigent-architecture.html`](Indigent-visuals/indigent-architecture.html) for a clickable, source-cited component map of the backend (rendered captures are in the [Screenshots](#screenshots-and-visuals) section).

## Technology Stack

| Layer | Technology | Responsibility in this project |
|---|---|---|
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4, shadcn/ui, lucide-react, pnpm | Workbench UI: conversation stream, context panel, sovereignty monitor, models, audit timeline, documents, knowledge, P&ID viewer |
| Frontend proxy | Next.js route handler (`app/api/[...path]/route.ts`) | Server-side streaming proxy to backend; keeps the backend address out of the client bundle |
| Backend | Python 3.11+, FastAPI, pydantic v2, pydantic-settings | HTTP API, SSE streaming, request validation, error envelope |
| Persistence | SQLite (WAL), `aiosqlite` | Tasks, events, files, artifacts, append-only audit log, sovereignty counters |
| Streaming | `sse-starlette` | Server-Sent Events with `Last-Event-ID` replay and keep-alives |
| Local inference | Ollama (HTTP client only — no SDK imports) | Open-weight text/vision models and embeddings (loopback) |
| Dev/test inference | Groq HTTP client (opt-in) | Explicit development/testing provider; never a fallback |
| Vector storage | Qdrant (Docker Compose, loopback) | Evidence vectors, document-scoped retrieval |
| Document parsing | PyMuPDF (`fitz`) | Local PDF text extraction; OCR adapter with mock for hermetic tests |
| Artifact generation | `python-docx`, `openpyxl` | DOCX reports and XLSX workbooks |
| Sandboxing | Docker SDK + `sandbox/Dockerfile` | Network-isolated, read-only code execution |
| Images | Pillow | Image handling for uploads/P&ID intake |
| HTTP | httpx | Provider transport, readiness checks |
| Testing | pytest, pytest-asyncio, ruff | Backend test suite, async tests, lint gate |
| Config | dotenv / `.env` (pydantic-settings), `.env.example` | Environment configuration, no secrets committed |

## Repository Layout

```text
indigent/
├── AGENTS.md                  # Governing rulebook (product, ownership, security invariants)
├── build.prd.md               # Backend build PRD (Soham's scope)
├── Progress.md                # Build progress tracker
├── pyproject.toml             # Project metadata, dev extras, pytest/ruff config
├── requirements.in            # Direct dependencies (source for the lock file)
├── requirements.lock          # Pinned lock file installed by `make setup`
├── .env.example               # All non-secret settings with defaults
├── docker-compose.yml         # Qdrant only (loopback, telemetry disabled)
├── Makefile                   # setup / run / test / demo / groq-dev targets
├── app/
│   ├── main.py                # FastAPI factory: middleware, errors, egress guard, routers
│   ├── config.py              # Settings (pydantic-settings) + model inventory validation
│   ├── deps.py                # Explicit stub/real service composition (JOY_MODULES switch)
│   ├── errors.py              # AppError hierarchy and error codes
│   ├── contracts/             # Frozen pydantic contracts + typing.Protocol interfaces
│   ├── api/                   # chat, tasks, files, knowledge, artifacts, models, monitoring, pid, health
│   ├── core/                  # db, schema.sql, repo, events, audit, workspace, files, artifacts, taskrunner
│   ├── runtime/               # registry, executor, sandbox, hardware, generators (docx, xlsx)
│   ├── net/                   # egress_guard, sovereignty
│   ├── policy/                # allow-list (seeded from G7) + validator schemas
│   ├── stubs/                 # Explicit stubs: orchestrator, policy, rag, pid, ml_tools, models_status, artifact_validator
│   ├── agent/                 # Joy-owned: orchestrator, router, registry, resource_manager, verification (real)
│   ├── providers/             # Joy-owned: ollama, groq, http, types (real)
│   ├── rag/                   # Joy-owned: production RAG, chunking, extractors, ocr, retrieval, store
│   ├── pid_ml/                # Joy-owned: P&ID pipeline internals
│   └── artifact_validation/   # Joy-owned: artifact semantic checks
├── sandbox/
│   ├── Dockerfile             # indigent-sandbox:1 image
│   └── selftest.py            # Container self-test
├── tests/                     # Backend test suite (mirrors app/) incl. tests/integration/
├── tools/contract_check.py    # Async CLI that validates every documented API endpoint
├── docs/
│   ├── api-contract.md        # Frozen API contract v1 (all endpoints and error codes)
│   ├── decisions.md           # Append-only decision log
│   ├── contract-mismatches.md # Frontend/backend contract drift ledger
│   ├── network-lockdown.md    # Host firewall guidance (macOS pf / Windows Defender)
│   └── demo-runbook.md        # Offline demo checklist and execution steps
├── Indigent-visuals/          # Architecture diagram (HTML) + rendered PNG captures
├── frontend/                  # (untracked in git) Next.js app + Frontend-fix.md remediation plan
└── data/                      # (gitignored) db.sqlite, workspaces/, uploads/, pid/, logs/, qdrant/
```

The **Soham / Joy** ownership boundary is documented in `AGENTS.md` (section G2): platform mechanisms (API, persistence, SSE, files, sandbox, monitoring) are platform-owned; intelligence modules (`app/agent/`, `app/providers/`, `app/rag/`, `app/policy/`, `app/artifact_validation/`, P&ID internals) are Joy-owned. The `JOY_MODULES=stub|real` setting selects which composition is wired, explicitly, with no try-import fallback.

## Use Cases

The following are illustrative scenarios. The framework that supports them (task lifecycle, tools, retrieval, artifacts, approval, audit) is implemented; **demarcation of which parts are operational today vs. proposed** is called out per scenario.

| Use case | Target user | Operational today | Output | Notes |
|---|---|---|---|---|
| Inspection report analysis | Inspection engineers | Partial — workflow + retrieval + DOCX generation implemented; real OCR/vision and end-to-end acceptance pending | Inspection summary/note draft | Evidence-linked where retrieval is used |
| SOP search and retrieval | Plant / engineering staff | Yes — knowledge ingestion, document-scoped retrieval, grounded answers validated | Cited answers from internal SOPs | Requires local embedding + Qdrant |
| Inspection report → approval note | Department head | Framework implemented (APPROVAL gate, DOCX) | Reviewed and approved `.docx` note | Approval requires a named approver |
| Confidential code assistance | Engineering software teams | Yes — coded tasks, sandbox execution, `code_package` artifact | Sandboxed code + result package | Docker required; network disabled |
| Spreadsheet analysis | Finance / projects | Yes — `create_xlsx` generator with computations | `.xlsx` workbook | Generator spec is bounded |
| P&ID-based knowledge exploration | Process engineers | Partial — `/api/pid/analyze` route + `PIDGraph` contract; real graph extraction pending (stub returns empty graph) | Graph JSON + overlay artifact | Needs Joy's real pipeline for meaningful output |
| Secure isolated computation | R&D / contractor code | Yes — Docker sandbox with network none | Execution results | Fails loudly if Docker unavailable |
| Local document knowledge management | Knowledge admins | Yes — background ingestion with per-file status | Ready-to-retrieve documents | No external embedding services |

Indigent is **not** a control system: it does not actuate industrial equipment, and no scenario implies autonomous operation. Engineering conclusions always require qualified human review (see [Disclaimer](#disclaimer)).

## Quick Start

### Prerequisites

- **Python 3.11+** (the lock file is installed with `pip`; see `requirements.in` for the rationale).
- **Docker** with the Docker engine running — required for the sandbox image. If Docker is unavailable the sandbox fails loudly (`SANDBOX_UNAVAILABLE`) — it never falls back to a host subprocess.
- **Ollama** running locally on `http://localhost:11434` with the models you want to use already pulled (`ollama pull <model>`).
- **Qdrant** via the provided Compose file (for the real RAG path).
- A POSIX shell or Windows PowerShell for the commands below.

### 1. Clone and set up the backend

```bash
git clone https://github.com/Som007-builds/indigent-dev.git
cd indigent-dev
make setup          # creates .venv, installs requirements.lock, builds the sandbox image
```

On Windows (or without `make`), run the equivalent manually:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.lock
docker build -t indigent-sandbox:1 sandbox/
```

### 2. Configure the environment

```bash
cp .env.example .env
```

`.env` contains no secrets — see [Configuration](#configuration). For a real-mode run you must:

- set `INFERENCE_MODE=local` (default) and the matching `LOCAL_HARDWARE_PROFILE` (e.g. `mac_silicon` on Apple Silicon);
- provide `MODEL_INVENTORY_JSON` (a JSON array of model records with `model_id`, `provider`, `mode`, `task_capabilities`, `hardware_profiles`, `memory_estimate_mb` — see `app/config.py`);
- for production RAG, provide `EMBEDDING_MODEL` and `EMBEDDING_VECTOR_SIZE` matching an operator-provisioned local Ollama embedding model.

For a stub-mode smoke test (no models, no Qdrant), leave these blank — the stub composition reports honestly empty model state.

### 3. Start the infrastructure and backend

```bash
docker compose up -d qdrant     # Qdrant (loopback, telemetry disabled)
make run                        # uvicorn app.main:app on 127.0.0.1:8000
```

The backend binds **127.0.0.1 only**. Verify it:

```bash
curl http://127.0.0.1:8000/healthz        # {"ok": true}
curl http://127.0.0.1:8000/readyz         # per-dependency check
curl http://127.0.0.1:8000/api/monitoring/sovereignty   # AIR-GAPPED in local mode
```

> The current representative real-mode path — validated in live tests — is local Ollama inference with `qwen3:14b` (default generation model on the Apple Silicon profile) or `qwen3.8-27b-abliterated:latest` (27B, validated for grounded answers), `embeddinggemma:latest` (768-dimension) for embeddings, and Qdrant for retrieval. Which models are *routable* is determined by `MODEL_INVENTORY_JSON`, which the operator provisions.

### 4. Run the frontend (optional, for the full UI)

```bash
cd frontend/ai-harness-sih-main
pnpm install
cp .env.example .env.local        # BACKEND_URL=http://127.0.0.1:8000 (server-side only)
pnpm dev                          # Next.js on http://localhost:3000
```

The browser never talks to the backend directly: `app/api/[...path]/route.ts` proxies `/api/*` server-side, streaming SSE without buffering.

### 5. Run the tests

```bash
make test                         # python -m pytest -q
python -m pytest -q -m "not docker"       # when the Docker daemon is unavailable
python -m ruff check .            # lint gate
```

Frontend gates: `pnpm typecheck`, `pnpm build`, `pnpm lint`.

## Configuration

All settings are read from `.env` (or the file named by `INDIGENT_ENV_FILE`) and validated by `app/config.py`. No secrets live in `.env.example`. Secrets (e.g. `GROQ_API_KEY`) are never logged, never stored in the audit log, and never returned by the API.

| Variable | Default | Purpose |
|---|---|---|
| `INFERENCE_MODE` | `local` | `local` or `groq`. Must be one of the two or the app refuses to start. |
| `LOCAL_HARDWARE_PROFILE` | `mac_silicon` | `mac_silicon` or `rtx_3050a_4gb`; must match the model inventory or routing fails closed. |
| `GROQ_API_KEY` | *(empty)* | Dev/test only; read by the Groq provider, never logged. |
| `JOY_MODULES` | `stub` | `stub` or `real` — selects the service composition explicitly. |
| `MODEL_INVENTORY_JSON` | *(empty)* | JSON array of model records; required by the real model layer. |
| `RESOURCE_MAX_CONCURRENCY` | `1` | Admitted concurrent model requests. |
| `HARDWARE_RAM_BUDGET_MB` / `HARDWARE_VRAM_BUDGET_MB` | *(blank)* | Optional fixed budgets; blank means "measure this machine". |
| `EMBEDDING_BACKEND` / `EMBEDDING_MODEL` / `EMBEDDING_VECTOR_SIZE` | — | Production RAG: a locally provisioned Ollama embedding model and its real output dimension. |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | Backend bind address (loopback only). |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000` | Comma list; inert in the normal setup because the browser only calls the same-origin proxy. |
| `DATA_DIR` | `./data` | Root for SQLite, workspaces, uploads, PID files, logs, Qdrant data. |
| `OLLAMA_BASE_URL` / `QDRANT_URL` | `http://localhost:11434` / `http://localhost:6333` | Loopback-only service URLs (readiness + provider transport). |
| `QDRANT_COLLECTION` | `indigent_evidence` | Qdrant vector collection name. |
| `MAX_UPLOAD_MB` / `MAX_PID_IMAGE_MB` | `50` / `25` | Upload and P&ID image size limits (`413` when exceeded). |
| `MAX_MESSAGE_CHARS` | `20000` | Maximum chat message length. |
| `MAX_ACTIVE_TASKS` | `2` | Concurrent task capacity (`429` when exceeded). |
| `PER_TOOL_TIMEOUT_S` / `MODEL_GENERATION_TIMEOUT_S` / `HARD_TASK_TIMEOUT_S` | `30` / `60` / `300` | Tool, model-generation, and overall task timeouts. |
| `APPROVAL_TIMEOUT_S` / `PID_TIMEOUT_S` | `86400` / `120` | Approval wait and P&ID analysis timeouts. |
| `SANDBOX_IMAGE` / `SANDBOX_MEM_MB` / `SANDBOX_CPUS` / `SANDBOX_PIDS` | `indigent-sandbox:1` / `256` / `1` / `64` | Sandbox image tag and container resource limits. |
| `SANDBOX_OUTPUT_LIMIT_KB` | `64` | Per-stream output truncation cap. |
| `WORKSPACE_TTL_HOURS` | `24` | Scratch workspace cleanup window (outputs and audit are kept). |
| `LOG_LEVEL` | `INFO` | Backend log level. |

Frontend has exactly one setting of its own: `BACKEND_URL` (default `http://127.0.0.1:8000`), read **server-side only** in `lib/backend-origin.ts`. It is deliberately not `NEXT_PUBLIC_`, so the backend's address never ships in a client bundle.

Host firewall policy for a strict lockdown is documented in [`docs/network-lockdown.md`](docs/network-lockdown.md) (a manual deployment step — the application never modifies firewall state).

## Model Support

Model support is driven by `MODEL_INVENTORY_JSON` — the operator declares which model IDs are available, which task capabilities they cover, which hardware profiles they fit, their memory estimates, and whether they are enabled. The router then selects only declared, available, healthy candidates.

Documented operating models in this repository:

| Model | Role | Notes |
|---|---|---|
| `qwen3:14b` | Generation (text) | Referenced as the default generation model for the Apple Silicon profile |
| `qwen3.8-27b-abliterated:latest` | Generation (text) | 27B; validated in live grounded-answer tests (a measured generation took ~84s, which motivated raising `MODEL_GENERATION_TIMEOUT_S` in the operator `.env`) |
| `embeddinggemma:latest` | Embeddings | 300M, 768-dimension; the only embedder, never used for generation (enforced by Ollama capability gating, tested) |
| Qwen 2.5 family (`qwen2.5:3b/7b`, `qwen2.5-coder`, `qwen2.5-vl`) | Reference recommendations in the build PRD for constrained hardware | Deployment-dependent; must be declared in the inventory to be routable |

Groq-hosted open-weight models (e.g. `openai/gpt-oss-20b`) appear only in the **explicit dev/test mode** (`INFERENCE_MODE=groq`). In that mode the app logs `EXTERNAL INFERENCE ACTIVE`, the sovereignty response says so, and the sandbox still runs with `--network=none`. Local mode never silently switches to Groq.

General guidance, not guaranteed performance: required memory and latency depend on the model, quantization, context length, workload, and available RAM/VRAM. Smaller quantized variants fit constrained machines by design, but no specific latency or accuracy figures are claimed here — they require on-target benchmarking.

## Hardware and System Requirements

These are **workload-dependent**; the exact numbers depend on the chosen models and document load. The table below is a practical envelope based on the actual runtime dependencies, not a benchmark.

| Requirement | Notes |
|---|---|
| CPU | 64-bit; multi-core recommended (Ollama inference, PyMuPDF parsing, Docker) |
| System RAM | Enough for the OS, Docker, Qdrant, and the largest resident model + context window (e.g. a 27B Q4 model is in the 15–20 GB-class range before the rest of the stack) |
| GPU / VRAM | Optional for local text models (CPU inference works, slower); **required** for comfortable vision-model use. The `rtx_3050a_4gb` profile targets a 4 GB card; `mac_silicon` targets Apple Silicon unified memory |
| Disk | Model weights (several GB each), Qdrant data, workspaces/uploads/logs; leave generous headroom |
| OS | macOS (Apple Silicon), Windows, or Linux; Docker Desktop or Docker Engine required |
| Docker | Mandatory for `execute_code`/`run_tests`; app fails loudly without it |
| Network | None required at runtime in `local` mode; pull models/images **before** disconnecting for an offline demo |

Reference workload envelope documented in the build PRD: a 7B Q4 reasoning model plus a 1.5–3B Q4 coder and a Q4 vision model is designed to fit a 4 GB VRAM card; a 27B-class model is positioned for higher-spec machines. Validate with your own target models before committing.

## Security Architecture

Indigent implements defense in depth. The automated layers are enforced in code and covered by tests; the outer network layers are documented operator actions.

**Implemented and tested:**

- **Loopback-only backend.** The API binds `127.0.0.1`; nothing off the machine can reach it.
- **Model output is never trusted authority.** Every tool call needs `PolicyDecision(allowed=True)` from the policy validator, and the runtime re-checks the decision against the per-task-type allow-list before executing.
- **Fail-closed validation.** Unknown tools, unexpected arguments, path traversal, and absolute-path escapes are rejected (`PATH_REJECTED`) before anything runs; every path derived from model/user input goes through `safe_join()` and workspace-containment checks.
- **Sandbox isolation.** Docker containers run `--network=none`, read-only root, dropped capabilities, `no-new-privileges`, no shell, PID/memory/CPU limits, `noexec` tmpfs, and a per-stream output cap. No host-subprocess fallback: sandbox unavailability is a loud `SANDBOX_UNAVAILABLE` error.
- **Process egress guard.** In local mode, socket-level connect/DNS wrappers deny everything except configured loopback services; denied attempts are counted and audited.
- **Bounded everything.** Timeouts at tool, model, and task level; bounded message/upload/artifact sizes; bounded repair (3 attempts); bounded concurrency.
- **Append-only audit.** SQLite triggers reject UPDATE/DELETE on `audit_log`. Secrets are redacted on write (key/token/secret/authorization patterns and `gsk_…` strings); tool args are stored as names + sizes, never file contents.
- **Artifact integrity.** SHA-256 hashes on every artifact and file; downloads re-hash and refuse to serve tampered data (`ARTIFACT_CORRUPT` / `FILE_CORRUPT`, audited).
- **No LLM SDKs, no hidden fallback.** Only HTTP clients talk to Ollama/Groq; `INFERENCE_MODE` is config-only and never inferred.

### Security Considerations and Limitations

- Local deployment does not automatically mean secure deployment. The backend's protections are application-level; the host OS, accounts, and filesystem remain the operator's responsibility.
- Open-weight models may still produce incorrect, unsafe, or prompt-injected content. Input documents are treated as untrusted data.
- Document content can carry prompt injection; the classifier treats request text as untrusted, but defense-in-depth against sophisticated injection is ongoing hardening, not a shipped guarantee.
- Agent tools can cause harmful side effects if mis-configured. The allow-list, approval gate, and sandbox limits are the current controls; they are not a certificate of safety for every workflow.
- Containers require correct isolation and host configuration to be effective (kernel-level escapes are outside the application's control).
- Network isolation must be enforced and verified at the infrastructure level (host firewall rules in `docs/network-lockdown.md`); the egress guard is defense-in-depth, not a replacement.
- Generated engineering recommendations must be reviewed by qualified personnel before operational use. Indigent is **not** certified for safety-critical decisions or autonomous actuation.
- No regulatory compliance, security certification, or vulnerability-free status is claimed.

## Data Privacy and Sovereignty

**What happens to data in this system:**

- **Uploaded documents** are stored under `DATA_DIR/uploads/` (task files), `DATA_DIR/pid/` (P&ID images), or `DATA_DIR/workspaces/{task_id}/inputs/` — all local, all on the machine running the app.
- **Prompts, retrieved passages, generated content, and logs** are persisted in the local SQLite database (`db.sqlite`) and event/audit tables — never transmitted in `local` mode.
- **Model inference** is served by Ollama over loopback in `local` mode. If the operator provisions an embedding model, embeddings are also computed locally; the professional RAG adapter validates the model exists locally and never pulls a missing model.
- **Intermediate artifacts** (chunks, vectors, evidence) live in the local Qdrant collection under `data/qdrant/`.
- **Application logs** are written under `DATA_DIR/logs/` and redact secrets before write.

**What the code guarantees in `local` mode:** zero external model-inference calls (verified by tests), a socket-level egress guard denying non-loopback connections, a network-disabled sandbox, and live sovereignty counters that report `AIR-GAP VIOLATED` if any external counter moves — the UI can never show `AIR-GAPPED` for a mode or counter state the backend did not report.

**What is deployment-dependent:**

- Model weights are downloaded once by the operator (`ollama pull …`), and images by `docker build`/`docker pull` before first run — operator actions, not runtime app behaviour.
- Strict air-gapping (the machine physically/`pf`/firewall-isolated from external networks) is a deployment decision documented in `docs/network-lockdown.md` and proven at demo time by observing the sovereignty counters.
- The frontend loads its fonts from Google Fonts in the current dev setup (`next/font/google`) — in an offline deployment these must be self-hosted or removed. **This is a known deployment-dependent external reference to review before an offline demo.**

Different assurance levels, stated plainly:

1. **No external model inference calls** — true in `local` mode.
2. **No application-level external service calls at runtime** — true in `local` mode (loopback-only). The Google-Fonts reference above is a frontend asset dependency, not a runtime data channel; the browser in dev fetches it once. Review and self-host for offline.
3. **Strictly enforced network isolation** — enforced at app level (sandbox `network=none`, egress guard); requires host firewall rules for a complete posture.
4. **A genuinely air-gapped deployment** — achievable with the documented offline checklist (pre-pull models/images, then disconnect); verify with the Sovereignty Monitor at demo time.

## Expected Demonstration Workflow

### Inspection Report to Approval Note

The primary SIH demonstration narrative:

1. An authorized employee opens the locally deployed Indigent workbench.
2. The employee uploads a sample scanned inspection report.
3. The application processes the document through its intake and (where provisioned) OCR/multimodal pipeline.
4. The agent extracts relevant findings and supporting evidence.
5. The agent retrieves applicable organizational SOPs from the local knowledge base (implemented; requires provisioned embeddings + Qdrant).
6. The system drafts an inspection summary and approval note.
7. The user reviews the output and approves it through the `APPROVAL` gate (implemented).
8. The application generates a downloadable Word document (implemented).
9. Execution logs record actions and results (implemented — audit timeline + SSE events).
10. The Sovereignty Monitor shows zero external calls in local mode (implemented).

Steps 3 and 5 carry the largest "pending real pipeline" dependency on OCR/vision; see [Roadmap](#roadmap).

### Scenario A: Task-Specific Model Selection

Submit a document summarization task and a coding task, and observe the classifier, `model_selected` event, routing badge in the UI, and audit log entries. Automatic routing is implemented in the real control plane and is only as useful as `MODEL_INVENTORY_JSON` — route with models actually provisioned on the machine.

### Scenario B: Sandboxed Code Execution

Submit a coding task (or attach code), let the agent write it, execute it in the Docker sandbox with `network_mode="none"`, and verify that (a) the output is returned, (b) the sandbox container block is in the audit timeline, and (c) the sandbox network is disabled as reported. This scenario is implemented end-to-end, including the `code_package` artifact.

## Screenshots and Visuals

The repository contains a live, source-cited architecture diagram (generated with the Archify skill) plus rendered captures:

| Asset | Description |
|---|---|
| [`Indigent-visuals/indigent-architecture.html`](Indigent-visuals/indigent-architecture.html) | Clickable component map of the backend with file/line citations |
| [`indigent-architecture.visual-check.1440x900.light.png`](Indigent-visuals/indigent-architecture.visual-check.1440x900.light.png) | Rendered capture, light theme |
| [`indigent-architecture.visual-check.1440x900.dark.png`](Indigent-visuals/indigent-architecture.visual-check.1440x900.dark.png) | Rendered capture, dark theme |

<!-- TODO: Add a genuine screenshot of the Indigent workbench (conversation stream + context panel + sovereignty bar). -->
<!-- TODO: Add a genuine screenshot of the model selection view. -->
<!-- TODO: Add a genuine screenshot of the audit timeline / execution timeline. -->
<!-- TODO: Add a genuine screenshot of the P&ID viewer with a real overlay artifact. -->

## API Reference

**Base URL:** `http://127.0.0.1:8000` (loopback only — nothing else can reach it).

**Common headers on every response:** `X-Request-ID`, `X-Inference-Mode: local|groq`.

**Errors:** every 4xx/5xx uses `{"error": {"code", "message", "request_id", "task_id"?}}`. Core codes: `NOT_FOUND 404`, `VALIDATION_ERROR 422`, `CONFLICT 409`, `PAYLOAD_TOO_LARGE 413`, `UNSUPPORTED_MEDIA 415`, `TASK_CAPACITY 429`, `TOOL_NOT_ALLOWED 403`, `PATH_REJECTED 400`, `SANDBOX_UNAVAILABLE 503`, `ARTIFACT_CORRUPT 500`, `INTERNAL 500`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness probe |
| `GET` | `/readyz` | Dependency readiness (sqlite, docker, sandbox_image gate 503; qdrant/ollama informational) |
| `POST` | `/api/chat` | Create a task; responds `text/event-stream` (first event `task_created`), header `X-Task-Id`. Disconnect does not cancel the task. `429` at capacity |
| `GET` | `/api/tasks` | List recent tasks |
| `GET` | `/api/tasks/{id}` | Full task state (plan, state, model, tool calls, chunks, artifacts, verification, final result) |
| `GET` | `/api/tasks/{id}/stream` | Join/replay a task's SSE stream (honors `Last-Event-ID`, no gaps) |
| `GET` | `/api/tasks/{id}/timeline` | Audit entries for a task, ordered by id |
| `POST` | `/api/tasks/{id}/approve` | `{approver, decision: approve|reject, note?}` — `409` unless state is `APPROVAL` |
| `POST` | `/api/files/upload` | Multipart upload (repeated `file`, optional `task_id`) — magic-byte verified |
| `GET` | `/api/files` · `/api/files/{id}` | List files · metadata + `?download=1` (re-hashes before serving) |
| `POST` | `/api/knowledge/upload` | Ingest knowledge documents (background RAG ingestion) |
| `GET` | `/api/knowledge` · `/api/knowledge/{file_id}` | List knowledge docs · per-file ingestion status |
| `GET` | `/api/artifacts/{id}` | Artifact manifest + `download_url`; `?download=1` streams the file (re-hashed) |
| `GET` | `/api/models` | Model registry status (mode, hardware profile, models, residency, resources) |
| `POST` | `/api/models/active` | Record an explicit active-model selection |
| `GET` | `/api/monitoring/sovereignty` | Sovereignty snapshot (counters, network policy, AIR-GAPPED/AIR-GAP VIOLATED status) |
| `POST` | `/api/pid/analyze` | P&ID analysis of an uploaded image → `PIDGraph` + artifacts |

SSE events follow a typed envelope (`task_created`, `state_changed` (with `task_type` on classification), `message`, `plan`, `model_selected`, `tool_proposed`, `policy_decision`, `tool_result`, `retrieval`, `verification`, `repair`, `artifact_created`, `artifact_validation`, `pid_graph`, `approval_requested`, `approved`/`rejected`, `completed`/`failed`). The full contract — payloads for every endpoint and every event — is frozen in [`docs/api-contract.md`](docs/api-contract.md), and `tools/contract_check.py` validates the live API against it end-to-end.

## Testing and Validation

### Backend

```bash
make test                        # python -m pytest -q
python -m pytest -q -m "not docker"        # without a Docker daemon
python -m ruff check .           # lint gate (ruff, line-length 100)
```

The suite is hermetic (it never inherits a developer's `.env`) and covers: configuration and model inventory validation; task lifecycle, SSE replay, capacity and approval flow; policy enforcement and path safety; file upload/intake and magic-byte checks; artifact registration, integrity and tamper detection; sandbox isolation and resource limits; RAG ingestion/retrieval and citation verification; provider contracts; orchestration and repair bounds; the `/api/models` and sovereignty reporting agreements; and the frozen contract check (`tests/test_step3.py` wraps `tools/contract_check.py`).

Tests are marked `docker` (need the Docker daemon) and `needs_models` (need Joy's real modules and provisioned local models — the 22-case acceptance matrix is intentionally gated until those are present; stubs are never used to claim integration coverage). A bounded platform-core smoke run (task runner, approval, files/download, artifact sizing, task-type wiring) passes: **37 passed** in this checkout. Full-suite results depend on the environment — see [Troubleshooting](#troubleshooting) for the known environment-gated failures (Docker daemon absent; real-module router health checks against a local Ollama).

### Frontend

```bash
pnpm typecheck    # tsc --noEmit
pnpm build        # next build (SSG + route guards)
pnpm lint         # eslint
```

### Live validation

With Ollama + Qdrant up and `JOY_MODULES=real`, `tests/integration/` exercises real local generation (`test_live_grounded_answer.py`, `test_live_rag_pipeline.py`), real-mode composition, inference-mode reporting, and the control-plane wiring. The offline demo checklist is in [`docs/demo-runbook.md`](docs/demo-runbook.md).

### Proposed future validation matrix

Not yet implemented — proposed: model routing accuracy; document extraction quality; retrieval relevance; agent completion rate; citation grounding; sandbox isolation escapes; resource-limit enforcement under load; external network activity (repeatable egress proof); error handling fuzzing; hardware performance benchmarks on target profiles.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `SANDBOX_UNAVAILABLE` on code tasks | Docker daemon stopped, or `indigent-sandbox:1` not built | `docker info`; `docker build -t indigent-sandbox:1 sandbox/`; start Docker Desktop/engine |
| `/readyz` reports `docker`/`sandbox_image` fail | Same as above | Same fix; the 503 is by design |
| App refuses to start with a RAG configuration error | Real mode without `EMBEDDING_MODEL`/`EMBEDDING_VECTOR_SIZE`/collection | Provision a local Ollama embedding model and set the three `EMBEDDING_*` vars |
| No model available (`ModelUnavailableError`) | `MODEL_INVENTORY_JSON` missing/mismatched, model not pulled, or health check failing | `ollama list`; fix the inventory (profile/mode/task caps); `ollama pull <model>` |
| `LOCAL_HARDWARE_PROFILE` mismatch | Profile doesn't match any inventory record | Align the profile and inventory (`mac_silicon` vs `rtx_3050a_4gb`) |
| Qdrant unreachable (RAG tasks fail) | Qdrant not started or URL wrong | `docker compose up -d qdrant`; confirm `http://localhost:6333` |
| Frontend shows `BACKEND_UNREACHABLE` | Backend down, or `BACKEND_URL` wrong in the frontend server env | Start the backend; check `frontend/ai-harness-sih-main/.env.local` |
| SSE shows nothing in the UI | Buffering proxy (old `rewrites()` config) | Confirm `app/api/[...path]/route.ts` exists; the rewrite path was removed by design |
| Port conflict on 8000/11434/6333/3000 | Another service bound | `netstat -ano | findstr :8000` (Windows) / `lsof -i :8000` (macOS/Linux); stop the other process |
| Full pytest run hangs or a real-mode test stalls | A real-module test health-checks Ollama synchronously (router/`deps.py`) | Run with `-m "not docker and not needs_models"` for the hermetic subset; keep Ollama reachable for real-mode tests |
| `422 VALIDATION_ERROR` on upload | Extension or magic bytes unsupported (`415`) or oversized (`413`) | Check the allowed list and `MAX_UPLOAD_MB` |
| OCR not detected in a scanned PDF | Tesseract not installed (OCR is environment-dependent) | Install Tesseract or rely on the text-extraction path; see `app/rag/ocr.py` |
| Sandbox "exec format"/missing `pytest` | Stale sandbox image | Rebuild `indigent-sandbox:1`; `docker image prune` if space is tight |

Diagnostic one-liners: `curl http://127.0.0.1:8000/readyz` (per-dependency), `curl http://127.0.0.1:8000/api/monitoring/sovereignty` (counters), `docker ps` (sandbox/Qdrant), `ollama list` (models), and `python -m pytest -q -m "not docker"` (hermetic suite).

## Roadmap

### Implemented (verified in this repository)

- FastAPI backend with SSE streaming, gapless replay, detached task runner, capacity limits, approval pause.
- SQLite persistence in WAL mode with append-only audit (triggers) and sovereignty counters.
- Policy validation (allow-lists, argument schemas, path safety, fail-closed) with policy re-check inside the runtime.
- Docker sandbox (network-less, read-only, resource-bounded, no host fallback).
- File intake with magic-byte verification; DOCX/XLSX generators; artifact store with SHA-256 integrity manifests.
- Real control plane: provider abstraction, model registry, hardware-aware routing, resource manager, bounded orchestrator, verification, repair.
- Production RAG: extraction, chunking, local Ollama embeddings, Qdrant store, document-scoped retrieval, citation verification.
- Sovereignty: socket egress guard, live counters, `AIR-GAPPED`/`AIR-GAP VIOLATED` reporting, `X-Inference-Mode` header on every response.
- Frontend: workbench with same-origin streaming proxy, sovereignty monitor, model page, audit timeline, P&ID viewer shell, documents/knowledge pages — with the "never display data the backend didn't send" honesty rule enforced.
- Contract tooling: `tools/contract_check.py` validates every documented endpoint.

### In Progress

- P&ID production graph extraction (owned by Joy; the stub currently returns an honest empty graph) and servable overlay artifacts.
- Full multimodal runtime transport to a local vision model (`OllamaProvider.generate_with_images` exists; end-to-end demo acceptance pending).
- End-to-end artifact/demo acceptance across all task types, including real-OCR document workflows.
- Hardening: prompt-injection defenses, resource-exhaustion/attack testing, sandbox escape validation, and the deferred approval-gate UI polish (composer state while a task waits in `APPROVAL`).

### Planned (proposed, not yet built)

- More robust automatic multi-model routing and hardware-aware model selection heuristics.
- Broader document and office deliverable formats (e.g. PPTX explicitly not built).
- Stronger prompt-injection defenses and more comprehensive policy controls.
- More extensive execution provenance and reproducible audit export.
- Enhanced offline deployment tooling (single-bundle installer, self-hosted assets).
- Live SCADA integration and sensor overlays — future direction only.
- Federated learning and on-device model adaptation — future research directions only.
- Human-in-the-loop industrial actuation — only with a separately validated safety and authorization architecture.

## Contributing

Contributions are welcome as long as they respect the security and sovereignty boundaries. Specifically, don't:

- introduce silent cloud fallbacks or mode switching;
- bypass policy validation (model output must never authorize a tool);
- add unrestricted agent loops (everything is bounded);
- weaken workspace, path, or sandbox isolation;
- add external network dependencies to offline execution paths;
- commit secrets, or sample documents that shouldn't be public.

Prefer deterministic validation over LLM-based validation wherever you can, and keep provenance intact whenever data moves through the system.

Suggested workflow:

```bash
git clone https://github.com/Som007-builds/indigent-dev.git
git checkout -b feat/your-change
# make your change; keep AGENTS.md ownership boundaries in mind
python -m ruff check .
python -m pytest -q -m "not docker"
pnpm --dir frontend/ai-harness-sih-main typecheck
git commit -m "feat: concise summary of the change"
git push -u origin feat/your-change
# open a pull request describing the change, tests, and evidence
```

There is no formal contribution governance document yet (`CONTRIBUTING.md` does not exist) — the rules above and the ownership boundary in `AGENTS.md` are the current contract. Welcome areas: agent orchestration, model integration, multimodal document processing, retrieval and knowledge management, sandbox security, enterprise deployment, and testing/documentation.

## License

License: Not yet specified. Please check the repository for licensing information.

## Acknowledgements and References

- **Ollama** — local model runtime: <https://ollama.com/>
- **Qdrant** — vector search engine: <https://qdrant.tech/>
- **FastAPI** — API framework: <https://fastapi.tiangolo.com/>
- **Next.js** — frontend framework: <https://nextjs.org/>
- **Docker** — sandbox isolation: <https://docs.docker.com/>
- **PyMuPDF** — local PDF text extraction: <https://pymupdf.readthedocs.io/>
- **OpenQwen models** — reference open-weight families used in this project (Qwen2.5 / Qwen3): <https://ollama.com/library/qwen3>
- **Smart India Hackathon 2026** — problem statement 26117: <https://www.sih.gov.in/>
- Team **Codecels** — problem statement context and demo

Relevant open literature on air-gapped and on-premise enterprise LLM deployment is deliberately not cited here unless it is verified: no third-party research findings, partnerships, or endorsements are claimed.

## Team and Project Information

| Field | Value |
|---|---|
| Project | Indigent — Sovereign Agentic AI Workbench |
| Team | Codecels |
| Hackathon | Smart India Hackathon 2026 |
| Problem Statement | 26117 — Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work |
| Theme | Smart Automation |
| Repository | <https://github.com/Som007-builds/indigent-dev> |

Project contact: please use the repository's issue tracker. No personal profiles, emails, or institutional affiliations are listed because none were verified for this document.

## Disclaimer

Indigent is an active development project. Its maturity must be assessed against the current release; features described as implemented are verified in this repository, while anything described as planned, proposed, or deployment-dependent is not a product claim.

AI-generated outputs may contain errors or omissions. Engineering calculations, inspection findings, technical analyses, and approval documents produced with or by this system require appropriate qualified human review before any operational use.

Indigent is not an autonomous safety-control or industrial actuation system. It must not be used to actuate or control industrial equipment unless a separately validated safety architecture and authorization framework has been established.

Organizations must independently assess their security, privacy, regulatory, infrastructure, and operational requirements before deploying Indigent with confidential data. Actual sovereignty and offline guarantees depend on verified implementation and deployment configuration — including the host firewall posture documented in `docs/network-lockdown.md` and the offline checklist in `docs/demo-runbook.md`.