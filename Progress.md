# Indigent Backend — Progress Tracker

**Last Updated:** 2026-09-27  
**Legend:** ✅ Done · 🟡 Partial · ⬜ Not started · 🔴 Blocked

---

## Soham — Platform Backend

| Step | What it delivers | Status | Notes |
|---|---|---|---|
| Step 0 | Skeleton, config, contracts, stubs, logging, errors | ✅ Done | FastAPI factory `/healthz`, JSON logger, secret redaction, `JOY_MODULES` switch. |
| Step 1 | SQLite persistence (WAL mode), schema migrations, append-only audit logger | ✅ Done | DB triggers enforce append-only audit log; automatic startup task recovery. |
| Step 2 | Task API, EventBus, TaskRunner, SSE streaming, `/api/chat`, approval pausing | ✅ Done | Background detached execution, gapless SSE replay (`Last-Event-ID`), capacity limits. |
| Step 3 | Frontend contract reconciliation, OpenAPI export, contract check tool | ✅ Done | `contract-mismatches.md`, `api-contract.md` v1 frozen, `tools/contract_check.py` passing. |
| Step 4 | File uploads, workspace creation, `safe_join` path safety, P&ID file intake | ✅ Done | Chunked streaming uploads, magic bytes check, path traversal prevention, P&ID intake. |
| Step 5 | Artifact store, SHA-256 integrity re-hashing, DOCX/XLSX report generators | ✅ Done | Manifest registration, tamper detection on download (500 ARTIFACT_CORRUPT), code packager. |
| Step 6 | Tool runtime, arg validation, isolated Docker sandbox execution | ✅ Done | Sandbox network disabled (`--network=none`), resource limits (CPU/RAM/PIDs), no host fallback. |
| Step 7 | Models status API, Sovereignty counters, socket-level process egress guard | ✅ Done | Real-time sovereignty status (`AIR-GAPPED`), loopback-only network egress enforcement. |
| Step 8 | Observability, `/readyz` probes, hourly workspace cleanup, graceful shutdown | ✅ Done | Readiness checks for DB/Docker/Qdrant/Ollama, task cancellation on shutdown. |
| Step 9 | Docker Compose setup (Qdrant), Makefile automation, network lockdown runbook | ✅ Done | Pinned Qdrant v1.19.1, developer Makefile targets, OS firewall documentation. |
| Step 10 | Real module integration, 22-case failure/security test matrix, demo runbook | ✅ Done | Real modules wired (`JOY_MODULES=real`); 21/22 integration tests green (1 opt-in Groq skipped). |

---

## Joy — AI Control Plane

| Area | What it delivers | Status | Notes |
|---|---|---|---|
| Inference Provider Layer | Ollama local model provider & Groq cloud provider adapters | ✅ Done | HTTP-based provider adapters (`OllamaProvider`, `GroqProvider`); zero LLM SDK imports. |
| Model Registry & Router | Hardware profile mapping, model loading, task-to-model routing | ✅ Done | Routes tasks to models; respects local hardware profile constraints. |
| Resource Manager | VRAM/RAM hardware budget enforcement and model residency tracking | ✅ Done | Dynamically tracks free memory; prevents over-allocation on host hardware. |
| Agent Orchestrator | Multi-step agent loop (INTAKE → COMPLETE) with event streaming & approval pause | ✅ Done | State machine execution, tool call generation, verification, and repair flow. |
| Policy Validation Layer | Tool call allowlist policy validator and parameter validation | ✅ Done | `PolicyValidator` checks `ALLOWED_TOOLS` per task type prior to tool execution. |
| RAG & Evidence Pipeline | Document chunking, Qdrant vector embedding, evidence retrieval & citation | ✅ Done | Uses `embeddinggemma:latest` (768d) & Qdrant vector store; live retrieval verified. |
| Multimodal/P&ID ML | Vision processing and P&ID graph extraction pipelines | 🟡 Partial | Routes to `MultimodalPIDPipeline`; missing local vision model & local OCR engine (e.g. tesseract). |
| Coding Model & Verification | Code generation, automated test execution, and repair iteration loop | ✅ Done | Handles code generation and iterative repair up to maximum attempt limits. |
| Artifact Validation | Inspection of generated deliverables (DOCX/XLSX/JSON) against quality rules | ✅ Done | `ArtifactValidator` checks deliverables and returns standard `ValidationReport`. |
| Sovereignty/ML Integration | External byte counting and air-gap verification integration | ✅ Done | `GroqProvider` reports bytes to `SovereigntyImpl`; local mode confirms `AIR-GAPPED`. |
| ML/Control-Plane Security Testing | Prompt injection defenses, citation verification, and error recovery testing | ✅ Done | Covered under joint integration test suite (`tests/integration/test_step10_matrix.py`). |

---

## Joint / Integration

| Group | Scenarios | Status | Notes |
|---|---|---|---|
| Local/Groq mode switching | Local chat E2E (Demo A), Groq mode, mode-isolation invariants, offline integrity | ✅ Done | Config-driven mode; local mode verifies `AIR-GAPPED` status; Groq calls tracked. |
| Sandbox isolation | Network blocking, host filesystem access denial, path traversal rejection, tool checks | ✅ Done | Docker `--network=none` prevents network egress; `safe_join` blocks path escapes. |
| Verification & repair loop | False citation detection, bad calculation rejection, code repair, runaway loop cap | ✅ Done | Verifier catches ungrounded claims; repair loop capped by `MAX_REPAIR_ATTEMPTS`. |
| Approval flow | Human approval gate pause/resume, rejection handling, approval timeout isolation | ✅ Done | Tasks pause at APPROVAL without burning execution timeout; state persisted to SQLite. |
| Audit completeness | Secret redaction, comprehensive event logging, graceful handling of model errors | ✅ Done | Every event logged with `inference_mode`; secrets redacted; clean error responses. |

---

## Blocking dependencies

- **Multimodal & P&ID ML**: Provisioning a local vision model for image analysis and installing a local OCR engine (e.g., Tesseract) for document OCR extraction.
- **Groq Mode Integration Test**: Live execution of matrix Row 2 requires an active `GROQ_API_KEY` (skipped by default as Groq is an opt-in non-air-gapped path).
- **RAM / VRAM Hardware Budgeting**: Running 27B LLM generation alongside Docker Desktop VM on 24 GB host requires explicit model release via keep-alive controls.

---

## How to update this file

- This file is updated manually by Soham after pulling Joy's commits.
- The AI agent edits this file only when explicitly requested, preserving history.
- Do not rewrite existing rows. When a status changes, append a single-line entry with date to the **Changelog** section below.

---

## Changelog

- **2026-09-27**: Initial creation of `Progress.md` populated with current audit results (Soham Platform Steps 0–10 complete; Joy Control Plane 10/11 areas complete, 1 partial; 21/22 Integration matrix scenarios passing).
