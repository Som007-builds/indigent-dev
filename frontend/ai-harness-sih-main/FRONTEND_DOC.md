# Sovereign On-Premise Agentic AI Workbench (AI-Harness)
## Frontend Engineering & Architecture Specification

**Document Version:** 2.0  
**Target Environment:** Local Air-Gapped Industrial / PSU / Defence Workstation  
**Stack:** React 19 · Next.js 16 (App Router) · Tailwind CSS v4 · TypeScript 5 · OKLCH Token System  

---

## 1. Executive Purpose & Frontend Mission

The AI-Harness Frontend is an **Industrial AI Workbench**, engineered specifically for confidential high-security workflows (refineries, defense, government enclaves). It is **not** a conventional consumer chat app or standard admin template.

### The 5 Scored Proofs the Frontend Delivers to Judges Live:
1. **Visible Multi-Step Agentic State Machine:** Every planning, tool-calling, verification, and repair transition is rendered in real time—never hidden behind a generic loading spinner.
2. **Dynamic Model Routing Transparency:** A **Routing Receipt Badge** (`Handled by: Coding LLM · qwen2.5-coder:7b | Reason: Python script attached`) is displayed inline on every response.
3. **Provable Zero Network Egress:** A persistent **Sovereignty Monitor** is permanently visible on-screen, proving zero external DNS/HTTP requests with real-time socket telemetry.
4. **Human-in-the-Loop Safety Gate:** The AI *recommends* and a human *approves*. Consequential actions stop at an interactive **Approval Gate** before completion.
5. **Real Industrial Deliverables & Graph Overlays:** Users can preview and download validated `.docx` notes, step-by-step `.xlsx` calculation sheets, and interact with a structured **P&ID Canvas/SVG Graph Viewer**.

---

## 2. Technical Stack & Dependencies

| Layer | Technology | Justification & Role |
| :--- | :--- | :--- |
| **Framework** | Next.js 16 (App Router) + React 19 | Fast server/client component model, type-safety, rapid build loop. |
| **Styling** | Tailwind CSS v4 + `@tailwindcss/postcss` | High-performance styling, native CSS variables, zero-runtime overhead. |
| **Color System** | OKLCH Semantic Tokens (`globals.css`) | Precise gamut control, consistent dark industrial theme, high readability. |
| **Icons** | `@hugeicons/react` / `@hugeicons/core-free-icons` | Clean, professional technical iconography. |
| **UI Primitives** | `@base-ui/react` + CVA + `clsx` + `tailwind-merge` | Accessible, unstyled primitives styled with custom tokens. |
| **Real-time Stream** | Native `EventSource` (Server-Sent Events) | Native browser SSE to stream agent state machine events and token deltas. |
| **State Management**| React Context + `useReducer` | Centralized task and telemetry state without external Redux/Zustand overhead. |

---

## 3. UI Layout & Wireframe Architecture

The workbench follows a **3-Pane Layout + 2 Persistent Global Strips**:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [TOP STRIP] SOVEREIGNTY MONITOR: [AIR-GAPPED: ACTIVE] [EXT CALLS: 0] [BLOCKED: 0] [LOCAL: 184]   │
├─────────────────┬───────────────────────────────────────────────┬────────────────────────────────┤
│   SIDEBAR       │           MAIN: CONVERSATION STREAM           │         CONTEXT PANEL          │
│                 │                                               │                                │
│ • New Task      │ [User Message: "Check corrosion report..."]   │ [Tabs: Files | Sources |       │
│ • Documents     │                                               │        Artifacts | P&ID Graph] │
│ • Knowledge     │ ┌───────────────────────────────────────────┐ │                                │
│ • Artifacts     │ │ 🏷 Routing Receipt: General Reasoning      │ │ • SOP-ENG-042 §4.2 (Page 17)   │
│ • Model Status  │ └───────────────────────────────────────────┘ │ • Measured Wall: 3.8mm         │
│ • Audit Logs    │                                               │ • Min Required: 4.5mm          │
│                 │ [Agent Step: Ingesting OCR scan...]           │                                │
│                 │ [Agent Step: Retrieved SOP-ENG-042...]        │ ┌────────────────────────────┐ │
│                 │ [Agent Step: Deterministic Calc (FAIL)...]    │ │ 📄 approval_note.docx      │ │
│                 │                                               │ │ 📊 calculation_sheet.xlsx  │ │
│                 │ ┌───────────────────────────────────────────┐ │ └────────────────────────────┘ │
│                 │ │ ⚠️ HUMAN APPROVAL GATE: Action Required    │ │                                │
│                 │ │ Recommendation: REJECT (Violates §4.2)    │ │ [Interactive P&ID Viewer]    │
│                 │ │ [Approve Note] [Modify] [Reject]          │ │ • Bounding Boxes & Pipelines │
│                 │ └───────────────────────────────────────────┘ │ • Node Inspector (FCV-101)   │
├─────────────────┴───────────────────────────────────────────────┴────────────────────────────────┤
│ [BOTTOM STRIP] AGENT EXECUTION TIMELINE: [✓ Intake] → [✓ OCR] → [✓ RAG] → [✓ Calc] → [⏳ Review] │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Component Specifications

### 4.1 SovereigntyMonitor (Persistent Global Header/Footer)
- **Role:** High-leverage persuasion component. Shows live telemetry that no packets leave the machine.
- **Visuals:** Dark technical pill with pulsing green indicator for `AIR-GAPPED`.
- **Metrics Displayed:**
  - `Network Status`: `AIR-GAPPED` (Green)
  - `Internet Access`: `BLOCKED` (Green / Shield Icon)
  - `External API Calls`: `0`
  - `External DNS Queries`: `0`
  - `Local Requests`: `<counter>`
- **Behavior:** Polls `/api/monitoring/sovereignty` every 1–2 seconds or receives SSE push updates.

### 4.2 RoutingReceiptBadge
- **Role:** Proves dynamic multi-model selection per task type.
- **Props:** `{ modelId: string, modelName: string, role: string, reason: string, vramResident: boolean }`
- **Visual:** Compact badge displayed immediately below user requests or at the start of agent responses:
  `⚡ Handled by: qwen2.5-coder:7b (Coding LLM) · Rule: Python file attached · VRAM: Active`

### 4.3 ConversationView & AgentStepAccordion
- **Role:** Renders user inputs, model explanations, and live agent execution progress.
- **States Rendered:**
  - `INTAKE / CLASSIFY`: Shows intent detection.
  - `PLAN`: Displays ordered bulleted plan.
  - `RETRIEVE`: Shows chunk cards with SOP source, section, and page tags.
  - `TOOL`: Shows tool name (`ocr_document`, `execute_code`), inputs, and outputs in collapsible code blocks.
  - `VERIFY / REPAIR`: Shows verification checks (e.g. unit tests running inside Docker sandbox, seeded test failure, repair attempt).
  - `MODEL_SWAP`: Displays an amber `"Swapping VRAM to Vision LLM..."` animation so the UI never appears frozen.

### 4.4 ApprovalGate (Human-in-the-Loop Sign-off)
- **Role:** Stops the state machine at the `APPROVAL` state before emitting finalized organizational actions.
- **Affordances:**
  - Recommendation summary banner (e.g., `Reject inspection: Wall thickness 3.8mm < 4.5mm threshold`).
  - Citations reference list.
  - Three action buttons:
    1. **Approve & Finalize Deliverables** (Green)
    2. **Request Re-analysis / Modify** (Amber)
    3. **Reject Recommendation** (Destructive Red)
- **Action:** Sends `POST /api/tasks/{task_id}/approve` with decision payload.

### 4.5 ContextPanel (Multi-Tab Intelligence Hub)
- **Tab 1: Files (`FilesTab`)**: Displays uploaded inspection scans, images, or source code files with thumbnail previews and OCR bounding box overlays.
- **Tab 2: Sources (`SourcesTab`)**: Shows all RAG knowledge chunks retrieved from Qdrant, complete with metadata tags (`SOP-ENG-042`, `Section 4.2`, `Page 17`).
- **Tab 3: Artifacts (`ArtifactsTab`)**:
  - Download cards for generated deliverables: `approval_note.docx`, `calculation_sheet.xlsx`, `report.pptx`, `solution.py`.
  - Includes validation badges (`✓ File Structure Validated`, `✓ Formulas Checked`).
- **Tab 4: P&ID Graph Viewer (`PIDGraphViewer`)**:
  - Dual view: Annotated image overlay + structured SVG/JSON graph explorer.
  - Clicking a node (e.g., `Pump P-101` or `Valve FCV-101`) highlights the corresponding bounding box on the P&ID diagram and displays connected pipelines and flow direction.

### 4.6 ExecutionTimeline (Task Progress Checklist)
- **Role:** Visual step-by-step progress checklist anchored to the task audit log.
- **Visuals:** Horizontal or vertical connected stepper:
  `[✓ 1. Upload] ── [✓ 2. OCR Extraction] ── [✓ 3. SOP RAG Match] ── [✓ 4. Calc Validation] ── [⏳ 5. Human Sign-off]`

---

## 5. TypeScript Data Models & Contracts

```typescript
// Task & Agent State Schema
export type TaskType = 'inspection' | 'coding' | 'pid_analysis' | 'general';

export type AgentState = 
  | 'INTAKE' 
  | 'CLASSIFY' 
  | 'PLAN' 
  | 'RETRIEVE' 
  | 'TOOL' 
  | 'VERIFY' 
  | 'REPAIR' 
  | 'ARTIFACT' 
  | 'APPROVAL' 
  | 'COMPLETE' 
  | 'FAILED';

export interface RoutingReceipt {
  modelId: string;
  modelName: string;
  role: 'reasoning' | 'coding' | 'vision' | 'embedding';
  reason: string;
  isResident: boolean;
}

export interface AgentStep {
  stepId: string;
  state: AgentState;
  title: string;
  description?: string;
  tool?: string;
  toolInput?: any;
  toolOutput?: any;
  durationMs?: number;
  status: 'pending' | 'running' | 'passed' | 'failed' | 'repaired';
  timestamp: string;
}

export interface SOPCitation {
  source: string;        // e.g. "SOP-ENG-042"
  section: string;       // e.g. "Section 4.2"
  page: number;          // e.g. 17
  snippet: string;
  confidence: number;
}

export interface ArtifactDeliverable {
  id: string;
  filename: string;
  fileType: 'docx' | 'xlsx' | 'pptx' | 'py' | 'json';
  fileSize: number;
  downloadUrl: string;
  validationStatus: 'validated' | 'warning' | 'error';
  validationMessage?: string;
}

export interface PIDNode {
  id: string;
  tag: string;           // e.g. "FCV-101"
  symbolType: string;    // e.g. "control_valve", "centrifugal_pump"
  bbox: [number, number, number, number]; // [x, y, w, h]
  confidence: number;
}

export interface PIDEdge {
  fromNode: string;
  toNode: string;
  lineType: 'process_pipe' | 'instrument_line' | 'electrical';
  confidence: number;
}

export interface PIDGraph {
  nodes: PIDNode[];
  edges: PIDEdge[];
  overlayImageUrl: string;
  flowNarrative: string;
}

export interface SovereigntyMetrics {
  isAirGapped: boolean;
  internetBlocked: boolean;
  externalApiCalls: number;
  externalDnsQueries: number;
  externalConnections: number;
  localRequests: number;
  statusText: string;
}

export interface TaskState {
  taskId: string;
  userPrompt: string;
  taskType: TaskType;
  currentState: AgentState;
  routing: RoutingReceipt;
  steps: AgentStep[];
  citations: SOPCitation[];
  artifacts: ArtifactDeliverable[];
  pidGraph?: PIDGraph | null;
  requiresApproval: boolean;
  approvalStatus?: 'pending' | 'approved' | 'rejected';
  createdAt: string;
  updatedAt: string;
}
```

---

## 6. Real-Time SSE Event Protocol

The frontend communicates with `/api/chat` using standard Server-Sent Events (`text/event-stream`):

```typescript
// SSE Event Types received from FastAPI
export type SSEEvent = 
  | { event: 'task_created'; data: { taskId: string; taskType: TaskType } }
  | { event: 'routing_receipt'; data: RoutingReceipt }
  | { event: 'state_transition'; data: { fromState: AgentState; toState: AgentState; step: AgentStep } }
  | { event: 'token_delta'; data: { delta: string } }
  | { event: 'citation_added'; data: SOPCitation }
  | { event: 'tool_execution'; data: { tool: string; input: any; output: any; durationMs: number } }
  | { event: 'artifact_ready'; data: ArtifactDeliverable }
  | { event: 'pid_graph_ready'; data: PIDGraph }
  | { event: 'approval_required'; data: { recommendation: string; summary: string } }
  | { event: 'task_complete'; data: { summary: string } }
  | { event: 'task_error'; data: { error: string; state: AgentState } };
```

---

## 7. Color Palette & Status Convention

We adhere to the dark, technical design tokens specified in `globals.css` with semantic meaning:

| Status / Indicator | Color Token | Hex / OKLCH Example | Usage |
| :--- | :--- | :--- | :--- |
| **Verified / Air-Gapped** | Emerald / Green | `oklch(0.7 0.15 145)` / `#10b981` | Air-gapped active, verified tests, valid artifacts, approved notes. |
| **Pending / In-Progress** | Amber / Orange | `oklch(0.75 0.15 75)` / `#f59e0b` | Running agent step, swapping VRAM model, awaiting human approval. |
| **Blocked / Security Drop** | Red / Rose | `oklch(0.65 0.2 25)` / `#ef4444` | Sandbox test failure, blocked outbound packet (demonstrated live). |
| **Brand Accent & Routing** | Teal / Cyan | `oklch(0.511 0.096 186.391)` | Primary buttons, routing badges, selected P&ID graph nodes. |
| **Background & Surfaces** | Dark Industrial | `oklch(0.145 0 0)` to `oklch(0.205 0 0)` | Slate/zinc dark workspace panels. |

---

## 8. Frontend Development & Implementation Plan

### Step-by-Step Build Order
1. **Mock API & SSE Provider:** Create a lightweight mock hook (`useMockSSE`) simulating the 4 flagship workflows without needing the backend running.
2. **Workbench Layout & Shell:** Assemble the 3-pane layout (`Sidebar`, `ConversationStream`, `ContextPanel`, `SovereigntyHeader`).
3. **Sovereignty Monitor Strip:** Build the live telemetry widget with pulsing status and blocked packet counters.
4. **Conversation Stream & Routing Receipt:** Implement the message stream, inline routing badges, and step-by-step accordion cards.
5. **Human Approval Gate Modal/Banner:** Build the review widget with Approve, Modify, and Reject triggers.
6. **Artifacts & Citations Tabs:** Build the download cards for `.docx` and `.xlsx` with validation chips.
7. **P&ID Canvas/SVG Graph Viewer:** Build the interactive drawing overlay renderer with node hover/click inspection.
8. **Real Backend Integration:** Switch from `useMockSSE` to native `EventSource` connected to the FastAPI endpoints.

---

## 9. Verification & Demo Readiness Checklist

- [ ] **Sovereignty Visibility:** Verify Sovereignty Monitor strip remains visible across all navigation tabs.
- [ ] **Routing Badge:** Verify the badge displays the correct model name and trigger reason for both coding and inspection tasks.
- [ ] **Model Swap UX:** Ensure a loading badge appears when the router swaps from `qwen3:8b` to `qwen2.5-vl:7b`.
- [ ] **Approval Gate Action:** Verify that clicking **Approve** sends the payload and advances the task to `COMPLETE`.
- [ ] **Artifact Download:** Verify clicking `.docx` and `.xlsx` artifacts downloads valid binary files locally.
- [ ] **P&ID Graph Interaction:** Verify clicking a node on the JSON tree highlights the bounding box on the CAD drawing canvas.
