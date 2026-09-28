# Indigent Backend — Progress Tracker

**Last Updated:** 2026-09-27  
**Legend:** ✅ Done · 🟡 Partial · ⬜ Not started · 🔴 Blocked

---

## Soham — Platform Backend

| Step | What it delivers | Status | Notes |
|---|---|---|---|
| Step 0 | Skeleton, config, contracts, stubs, logging, errors | ✅ Done | FastAPI factory `/healthz`, JSON logger, secret redaction, `JOY_MODULES` switch. |
| Step 1 | SQLite persistence (WAL mode), schema migrations, append-only audit logger | ✅ Done | DB triggers enforce append-only audit log; automatic startup task recovery. |
| Step 2 | Task API, EventBus, TaskRunner, SSE streaming, `/api/chat`, approval pausing | ✅ Done | Background detached execution, gapless SSE replay (`Last-Event-ID`), capacity limits. Fixed TASK_TIMEOUT error code mismatch (was returning ORCHESTRATOR_ERROR on hard timeout) — 2026-09-27. Fixed `/api/models` mode-reporting bug (stub hardcoded `local` + wrong `max_concurrency`) — 2026-09-27, verified via 3-way live check (endpoint/header/sovereignty all agree). |
| Step 3 | Frontend contract reconciliation, OpenAPI export, contract check tool | ⚠️ Corrected 2026-09-28 — reconciliation was **not** complete when marked Done | `tools/contract_check.py` exists (async CLI, httpx+ASGITransport, validates all G11 endpoints incl. SSE, error envelopes, X-Inference-Mode header); tests/test_step3.py wraps it. But the frontend remediation (Phases 1–6 of `frontend/Frontend-fix.md`, 2026-09-27..28) found the reconciliation had missed real drift: 8 contract mismatches are now recorded with status in `docs/contract-mismatches.md` (e.g. no `GET /api/files/{id}`, no `active_model_id`, `isResident` vs `resident`, artifact sizes absent from G8, task-type drift). Closed on the platform side, one `joy`-flagged, one `open`. |
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
- ~~Unused dependencies: chromadb/onnxruntime~~ — RESOLVED 2026-09-27 (false premise): neither package is present in requirements.lock or pyproject.toml at all; nothing is or was blocked on this. See Changelog for full correction history.

---

## Open Items

Not tracked by the step tables above: work that is not part of a completed step, or that is handed off to another owner. Anything closed here should get a dated Changelog line.

| Item | Owner | Status |
|---|---|---|
| Flaky SSE test — `tests/test_step2.py::test_happy_stream_orders_events_and_task_survives_unsubscribed_client` | Soham | Logged, not yet investigated. High risk if it fires during a live demo. |
| Planner XLSX routing decision logic | Joy | `create_xlsx` is now visible in the planner tool menu; the decision logic for when to use it is not written. |
| Calculations block emission | Joy | Pass-through built on Soham's side (`grounded_artifact.py` → `ArtifactValidationContext`); no producer populates the field yet. |
| Grounded-answer DOCX-vs-XLSX routing decision | Joy | Currently hardcoded to DOCX always (`grounded_artifact.py`); needs an explicit decision. |
| P&ID overlay rendering | Joy | Vision model emits JSON only; there is no local renderer to produce the overlay PNG. |
| Lockfile Python-version mismatch (3.14 vs 3.11) | Joy | Problem stated, CVE guardrail documented; awaiting his decision on regeneration approach. |
| Debug `print()` in `app/agent/orchestrator.py:250` | Joy | Flagged, not fixed (outside Soham's scope). |
| Dead code `_run_grounded_with_evidence` (`app/agent/orchestrator.py:608`) | Joy | Flagged, not fixed. Defined with no callers. |
| Real end-to-end demo on `INFERENCE_MODE=local` with actual models | Whoever has target hardware | Not yet run; Soham's machine cannot run local models by design. |

---

## How to update this file

- This file is updated manually by Soham after pulling Joy's commits.
- The AI agent edits this file only when explicitly requested, preserving history.
- Do not rewrite existing rows. When a status changes, append a single-line entry with date to the **Changelog** section below.

---

## Changelog

- **2026-09-27**: Initial creation of `Progress.md` populated with current audit results (Soham Platform Steps 0–10 complete; Joy Control Plane 10/11 areas complete, 1 partial; 21/22 Integration matrix scenarios passing).
- **2026-09-27**: Fixed Step 2 TASK_TIMEOUT error code bug (test_orchestrator.py).
- **2026-09-27**: Built real tools/contract_check.py per Step 3 spec; corrected Step 3 row which previously overstated completion.
- **2026-09-27**: Fixed Windows-incompatible grep call in test_dependency_contract.py (replaced with pathlib/re scanner).
- **2026-09-27**: Confirmed chromadb/onnxruntime unused in app/ — flagged for Joy, lockfile left untouched pending his input.
- **2026-09-27**: Documented POST /api/tasks/{id}/approve fire-and-continue behavior in docs/api-contract.md.
- **2026-09-27**: Fixed /api/models mode-reporting bug — `StubModelsStatus` hardcoded `'local'` regardless of actual mode; also fixed matching `max_concurrency` hardcode (2 vs configured default 1). Added 9-case regression test suite (`tests/integration/test_inference_mode_reporting.py`). Real (non-stub) `ModelsStatus` was already correct — bug was stub-only.
- **2026-09-27**: Corrected docs/decisions.md — previously claimed chromadb/onnxruntime/numpy/scipy were stale lockfile entries; verified none are present in requirements.lock or pyproject.toml at all. Conclusion (Ollama is sole embedding backend) re-grounded in code (`OllamaEmbeddingAdapter`, `EMBEDDING_BACKEND` type) rather than the lockfile.
- **2026-09-27**: Note on the 2026-09-27 chromadb/onnxruntime entry above — re-verified: neither package exists in requirements.lock or pyproject.toml at all, so there was nothing to leave untouched for Joy on this point. Superseded by the decisions.md correction same day.
- **2026-09-27**: Consolidated open-items list — all Soham-side P0/P1 backend fixes complete (mode-reporting bug, Windows hardware detection, Groq hard-refuse, XLSX/calculations wiring on platform side, lockfile toolchain gap, OCR documentation, requirements.in reconstruction). Remaining open items are Joy-side (XLSX/calculations producer logic, P&ID overlay, lockfile regeneration decision) or require dedicated investigation (flaky SSE test) or external hardware (real-mode demo).
- **2026-09-28**: Frontend remediation Phases 1–6 of `frontend/Frontend-fix.md` — see `docs/decisions.md` for the detail. Corrected Step 3 above: reconciliation was not complete; `docs/contract-mismatches.md` created with 8 mismatches and status. Platform fixes included the streaming `/api/*` proxy, `GET /api/files/{id}`, artifact `size_bytes`, reverted `taskrunner` task_type pre-seed (owner decision), CORS default covering the Next.js origin.
