<!-- BEGIN:nextjs-agent-rules -->
# Next.js & Frontend Agent Guidelines

This is Next.js 16 (App Router) + React 19 + Tailwind CSS v4.
Read the relevant documentation in `node_modules/next/dist/docs/` before writing code and heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# AI-Harness Frontend Agent Rulebook

All frontend agents working in this directory **MUST** adhere to the master rulebook and design guidelines:

## 1. Documentation & Source of Truth
All paths are relative to this file (`frontend/ai-harness-sih-main/AGENTS.md`).

- **Root Agent Rulebook:** [`../../AGENTS.md`](../../AGENTS.md) — the governing
  document. G1 product, G2 the Soham/Joy ownership boundary, G3 the security invariants,
  G4 commands, G5 repo layout, G6 config, G7 locked decisions, G8 contracts, G9 events
  and audit, G10 database, G11 API contract, G12 workspace layout. **Read this before
  changing anything that touches the backend.**
- **Frontend Specification:** [`FRONTEND_DOC.md`](FRONTEND_DOC.md)
- **Design System & Tokens:** [`DESIGN.md`](DESIGN.md) & `app/globals.css`
- **Backend/API contract:** [`../../docs/api-contract.md`](../../docs/api-contract.md)
- **Recorded decisions:** [`../../docs/decisions.md`](../../docs/decisions.md) —
  append-only; read the tail before adding a line.
- **Network lockdown posture:** [`../../docs/network-lockdown.md`](../../docs/network-lockdown.md)
- **Frontend remediation plan:** [`../Frontend-fix.md`](../Frontend-fix.md) — the
  plan of record for the "stop displaying data the backend never sent" work.
- **Backend build PRD:** [`../../build.prd.md`](../../build.prd.md)

Links that used to be here and are deliberately **not** restored: `../DOCS/` and
`../DOCS/GENERAL_PROJECT_DOC.md`. There is no `DOCS/` directory anywhere in this
repository, and no `GENERAL_PROJECT_DOC.md`. The previous revision pointed at
`file:///home/johan/Hackathons/SIH2026/ai-harness/…` absolute paths from a different
machine, so every one of them was dead on arrival. The architecture content they
claimed to hold is in the root rulebook (G5 repo layout, G7 locked decisions) and
`build.prd.md`; if a genuine architecture document is ever written, link it here and
check that it resolves.

## 2. Skills Usage (`.agents/skills/`)
Before building or modifying components, consult installed skills in `.agents/skills/`:
- **`shadcn`** (`.agents/skills/shadcn`): For Shadcn UI and Base UI component additions/composition.
- **`ui-ux-pro-max`** (`.agents/skills/ui-ux-pro-max`): For UI layout, micro-interactions, and visual hierarchy.

## 3. UI Design System Guidelines (`DESIGN.md` & `globals.css`)
- **Theme:** Dark technical "Industrial AI Workbench" theme.
- **Spacing:** Strict 8px grid (`gap-2`, `p-4`, `p-6`).
- **Typography:** System-ui / Inter font stack; monospace for logs, timeline, P&ID tags, and routing badges.
- **Status Colors:**
  - **Green (`oklch(0.7 0.15 145)`):** Air-gapped active, verified tests, valid artifacts, human-approved.
  - **Amber (`oklch(0.75 0.15 75)`):** Running steps, model hot-swapping in VRAM, approval pending.
  - **Red (`oklch(0.65 0.2 25)`):** Blocked outbound packets (sovereignty demo), sandbox test failures.
  - **Teal / Cyan (`oklch(0.511 0.096 186.391)`):** Routing receipts, brand accents, selected graph nodes.

### Core Directives:
1. **Absolute Data Sovereignty:** Zero outbound network traffic. All inference, OCR, RAG, execution, and artifact generation are 100% local.
2. **General-Purpose & Senior-Accessible UX (STRICT):** Never build for technical users or developers. Design for everyday general-purpose users, plant managers, and senior government officials (must be clear, readable, and intuitive even for an 80-year-old). Never use tech fonts (`font-mono`), dense code dumps, or developer jargon in primary interfaces.
3. **Deterministic Orchestration:** Agents operate on a bounded state machine (`INTAKE` → `COMPLETE`) with typed Pydantic contracts and tool allow-lists, never unconstrained looping swarms.
4. **Human-in-the-Loop:** Sensitive decisions and deliverables mandate human sign-off via an explicit `APPROVAL` state.
5. **Real Deliverables:** Generates validated Word notes (`.docx`), step-by-step arithmetic check spreadsheets (`.xlsx`), structured P&ID connectivity graphs (`JSON` + Canvas/SVG overlay), and sandboxed code diffs.

## 4. Key UI Components & Layout
- **Top Global Bar:** `SovereigntyMonitor` (Real-time air-gap telemetry, blocked packet counters).
- **Sidebar:** Navigation (New Task, Documents, Knowledge Base, Artifacts, Models, Audit).
- **Main Stream:** Conversation view, streamed step accordion, inline **Routing Receipt Badge**, and **Approval Gate**.
- **Context Panel:** 4 Tabs (`Files`, `Sources`, `Artifacts`, `PIDGraphViewer`).
- **Bottom Bar:** `ExecutionTimeline` (Audit-log step checklist).

## 5. Data Honesty (STRICT — not negotiable)

**Never display a value the backend did not send.** This is the rule the whole frontend
remediation exists to enforce, and it outranks visual completeness.

Concretely, when the backend omits something:

- render an explicit absence — `lib/format.ts` exports `NOT_REPORTED` for exactly this;
- leave the field **null/optional** and narrow it away with a type guard, rather than
  defaulting it to a plausible value;
- **never** substitute a placeholder, a sample, a plausible-looking number, or a
  neighbouring field's value.

`taskType` is the worked example. It was `TaskType | 'general' | 'sovereignty_proof'`,
defaulted to `"general"` whenever the backend reported nothing. G7 defines exactly three
task types and CLASSIFY assigns one; "not classified yet" is a **null**, not a fourth
kind of task. Same class of defect as the `fileSizeFormatted: "Validated deliverable"`
string in a size field, and as `"Not reported"` invented per-site with different wording.

Two more rules that follow from the same principle:

- **Assert nothing the backend did not measure.** `AIR-GAPPED` must come from
  `GET /api/monitoring/sovereignty`, not from a hardcoded default. A monitor that
  claims air-gap before the backend has been contacted is worse than one that shows
  nothing.
- **No mock data, no mock toggle, in any shipped path.** `lib/mock-data.ts` is retained
  as a design fixture with a do-not-import banner; see the note at its head.

