# Indigent

**A sovereignty-first, self-hosted agentic AI workbench for industrial engineering work that can't leave the building.** Every model action gets proposed, checked against policy, run through tools, and verified before it becomes an approved artifact.

Built for **Smart India Hackathon 2026 · Problem Statement 26117**.

Status: Phase 1 (control plane) implemented and tested. Phases 2–4 are in progress. See [Current development status](#current-development-status).

[Why Indigent](#why-indigent) · [How it works](#core-principles) · [Quick start](#quick-start) · [Architecture](#architecture) · [Status](#current-development-status) · [Roadmap](#roadmap) · [Contributing](#contributing)

---

## Why Indigent

Companies need to keep sensitive data in-house: inspection reports, P&IDs, specs, maintenance logs, calculations, scripts, compliance docs. Most AI workflows assume that data can leave the building. Indigent doesn't. **Your data stays inside your own infrastructure.** Any exception is a config setting you choose explicitly, not a hidden fallback.

Indigent is more than a local LLM wrapper. It's a control plane between the model and the tools it uses. Upgrading the model doesn't automatically give it more permissions.

## Core principles

### 1. Sovereignty by construction

```bash
INFERENCE_MODE=local
```

Local mode has no silent fallback to a cloud provider. Groq is available as a sanctioned dev/testing option, kept separate from the default path. The shipped and demo configuration runs on local Ollama.

The platform also shows sovereignty as a live runtime state, not just a README claim:

```text
AIR-GAPPED
External API Calls: 0
Internet: BLOCKED
Inference: LOCAL
```

vs. explicitly:

```text
EXTERNAL INFERENCE ACTIVE
Network: ALLOWED TO PROVIDER ENDPOINT
```

### 2. Bounded autonomy

The agent runs through a fixed state machine with defined timeouts, authorization checks, and capped repair attempts at each stage:

```mermaid
flowchart TD
    A[INTAKE] --> B[CLASSIFY]
    B --> C[PLAN]
    C --> D[RETRIEVE]
    D --> E[TOOL]
    E --> F[VERIFY]
    F -->|fails| G[REPAIR]
    G --> F
    F -->|passes| H[ARTIFACT]
    H --> I[ARTIFACT_VALIDATE]
    I -->|invalid/unverified| G
    I -->|valid| J[APPROVAL]
    J --> K[COMPLETE]
```

### 3. Policy-controlled execution

We treat model output as an **untrusted proposal**, never a trusted instruction. Every tool request has to clear a deterministic policy validator before it reaches the execution runtime. The model can't authorize its own actions.

```mermaid
flowchart LR
    M[LLM output] --> T[ToolRequest]
    T --> P{Policy Validator}
    P -->|DENY| X[Rejected]
    P -->|ALLOW| R[Tool Runtime]
```

### 4. Evidence before confidence

We track where every piece of evidence came from instead of just returning similar-looking text chunks. Each piece of evidence carries a document ID, chunk ID, source hash, page/section reference, and retrieval/rerank scores, so it can be traced back to its source:

```
Document → Chunk → Evidence → Claim → Verification → Artifact
```

### 5. Verification is a first-class step

Nothing is trusted by default. We verify citations, evidence chains, math, code execution and tests, and artifact structure and semantics. If a check fails, we attempt repair and re-verify, up to three times. If something still can't be verified, it's recorded as **`UNVERIFIED`** instead of marked as passing.

---

## Architecture

```mermaid
flowchart TD
    U[User Task] --> O[Bounded Orchestrator]
    O --> TR[Task Router]
    O --> PL[Policy Layer]
    O --> RM[Resource Manager]
    TR --> PV[Providers]
    PL --> TRT[Tool Runtime]
    RM --> MS[Model State]
    PV --> OL[Ollama - local]
    PV --> GQ["Groq (dev/test only)"]
    OL --> TS[Task-specific systems]
    TS --> RAG[RAG / Evidence]
    TS --> COD[Coding / Tests]
    TS --> MM[Multimodal / P&ID]
    RAG --> AG[Artifact Generator]
    COD --> AG
    MM --> AG
    AG --> AV[Artifact Validator]
    AV --> HA[Human Approval]
```

### Security boundary

We treat the model as an untrusted decision-maker, never a trusted execution engine.

```mermaid
flowchart TD
    M["Model (UNTRUSTED)"] -->|proposes action| PV["Policy Validator (TRUST BOUNDARY)"]
    PV -->|authorized only| TR[Tool Runtime]
```

Other security properties: fail-closed validation, workspace confinement, path-traversal prevention, bounded file sizes, explicit tool allowlists, bounded retries, deterministic verification, no hidden provider fallback, provider isolation, and no credentials in model prompts or logs.

---

## Quick start

The repo currently ships the Joy control-plane implementation and its test suite. There's no end-to-end application yet (see [status](#current-development-status) below). You can install it and run the control plane itself:

```bash
# Install dependencies from the project configuration
pip install -r requirements.txt   # or the project's declared dependency file

# Run the full test suite
pytest -q

# Static compilation check
python3 -m compileall -q app tests
```

Expected result: **101 tests passing**, with no external network access required.

Local inference runs through [Ollama](https://ollama.com). Production config sets `INFERENCE_MODE=local`. Groq is only enabled deliberately, for development or testing.

---

## What's implemented

| Layer | Capabilities |
|---|---|
| **Inference & model control** | Provider abstraction, local Ollama provider, explicit Groq dev/test provider, health checks, explicit inference modes, model registry, task-aware routing, hardware-profile-aware selection, `ModelUnavailableError`, no silent cross-mode fallback |
| **Resource management** | Model residency tracking, active-request tracking, memory requirement config, bounded concurrency, load/unload hooks — no fabricated GPU telemetry |
| **Bounded orchestration** | Explicit execution states, dynamic planning hooks, task classification, retrieval integration, tool boundaries, verification, bounded repair, human approval, hard task/model/tool timeouts |
| **Policy validation** | Task/tool authorization, allowlists, argument validation, unexpected-field rejection, path-traversal and absolute-path rejection, workspace boundary enforcement, file type/size limits, fail-closed behavior |
| **RAG & evidence** | Document models, source hashing, text-extraction and OCR interfaces, deterministic chunking, stable chunk IDs, source offsets, evidence metadata, in-memory offline vector store, cosine similarity + lightweight reranking, provenance preservation |
| **Citation verification** | Claim-vs-evidence checking, structured output validation, confidence + explanation recording, provenance preservation, triggers bounded repair on failure |
| **Coding agent** | Generate → policy-validate → create → execute → test → deterministic verification → bounded repair, using exit codes/test results/runtime errors rather than asking an LLM if it worked |
| **Multimodal / P&ID** | Structured `PIDGraph` representation (nodes, edges, bounding boxes, confidence, overlay reference, narrative), graph validation for stable IDs, unique nodes, valid edges, confidence bounds |
| **Artifact validation** | Structural + semantic checks, claim/evidence linkage, citation validation, deterministic calculation checks, provenance checks, SHA-256 artifact hashing, explicit `VALID` / `INVALID` / `UNVERIFIED` states |

Supported hardware profiles today: **Mac Apple Silicon**, and **Windows/Linux with an RTX 3050A 4GB**.

The default global repair bound is:

```text
MAX_REPAIR_ATTEMPTS = 3
```

There is no unbounded self-correction loop anywhere in the system.

---

## Current development status

The repo contains the core Joy control-plane implementation and its tests. This is control-plane-first, not a wired-up end-to-end product yet.

**Implemented and tested**
- Inference provider abstraction, Ollama provider, Groq dev provider
- Model registry and router, resource manager
- Bounded orchestrator, tool policy validation
- RAG/evidence control layer, citation verification
- P&ID graph pipeline
- Coding verification/repair loop
- Artifact semantic validation and repair/revalidation
- Control-plane integration audit

**In progress**
- Production model inventory/configuration
- Full real-mode application wiring
- Provider → Resource Manager and sovereignty telemetry integration
- Production embedding / vector-store and OCR adapters
- Real multimodal provider transport
- Production artifact generation integration
- Full end-to-end execution paths
- Security/attack testing and demo hardening

We intentionally **fail closed** when production dependencies or adapters aren't configured, instead of silently substituting stubs or external services.

---

## Testing

```bash
pytest -q
```

The current focused test baseline is **101 passed**, covering provider behavior, model routing, resource management, orchestration, policy enforcement, RAG, citation verification, coding verification, P&ID parsing, artifact validation/repair, and application-wiring behavior. The suite runs without external network access.

---

## Project structure

```text
app/
├── agent/                 # orchestrator, router, registry, resource manager, state machine
│   ├── coding.py
│   ├── orchestrator.py
│   ├── registry.py
│   ├── resource_manager.py
│   ├── router.py
│   └── state.py
├── artifact_validation/
│   └── validator.py
├── policy/
│   ├── allowlist.py
│   ├── schemas.py
│   └── validator.py
├── providers/
│   ├── base.py
│   ├── groq.py
│   ├── http.py
│   ├── ollama.py
│   └── types.py
├── rag/
│   ├── chunking.py
│   ├── extractors.py
│   ├── interfaces.py
│   ├── models.py
│   ├── retrieval.py
│   ├── store.py
│   └── verification/
└── pid_ml/
    ├── models.py
    └── pipeline.py

tests/
├── integration/
├── test_coding.py
├── test_orchestrator.py
├── test_policy.py
├── test_rag.py
├── test_pid_pipeline.py
├── test_artifact_validation.py
└── ...
```

For generated code, tool calls resolve to a validated contract of this shape:

```json
{
  "files": [
    { "path": "code/main.py", "content": "print('hello')" }
  ]
}
```

---

## Configuration

This only documents settings that currently exist. The table will grow as production wiring lands.

| Variable | Required | Default | Description |
|---|---:|---|---|
| `INFERENCE_MODE` | Yes | — | `local` runs inference through Ollama with no cloud fallback; any external mode is an explicit, separately-configured development/testing path |
| `MAX_REPAIR_ATTEMPTS` | No | `3` | Global bound on how many times the orchestrator will attempt bounded repair before surrendering to an `UNVERIFIED`/`INVALID` result |

---

## Roadmap

| Phase | Focus |
|---|---|
| **1 — Control plane** *(current)* | Provider abstraction, model routing, resource management, orchestration, policy enforcement, verification, provenance |
| **2 — Runtime integration** | Real model inventory, real local inference, task/runtime wiring, coding execution, RAG ingestion/retrieval, artifact generation, sovereignty telemetry |
| **3 — Multimodal** | OCR, image transport, P&ID inference, structured graph extraction, multimodal verification |
| **4 — Hardening** | Security attack tests, network-egress validation, resource exhaustion tests, prompt-injection tests, artifact tamper validation, end-to-end demo workflows |

---

## Contributing

Contributions are welcome as long as you don't break the security/sovereignty boundaries. Specifically, don't:

- introduce silent cloud fallbacks
- bypass policy validation
- let model output authorize tools
- add unrestricted agent loops
- weaken workspace/path isolation
- add external network dependencies to offline execution paths

Prefer deterministic validation over LLM-based validation wherever you can, and keep provenance intact whenever data moves through the system.

**Local setup:**

```bash
pytest -q
python3 -m compileall -q app tests
```

---

## License

License TBD. Will be added with the release configuration.
