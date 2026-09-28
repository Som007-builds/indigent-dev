<!-- BEGIN:nextjs-agent-rules -->
# Next.js & Frontend Agent Guidelines

This is Next.js 16 (App Router) + React 19 + Tailwind CSS v4.
Read the relevant documentation in `node_modules/next/dist/docs/` before writing code and heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# AI-Harness Frontend Agent Rulebook

All frontend agents working in this directory **MUST** adhere to the master rulebook and design guidelines:

## 1. Documentation & Source of Truth
- **Root Agent Rulebook:** [`../AGENTS.md`](file:///home/johan/Hackathons/SIH2026/ai-harness/AGENTS.md)
- **Frontend Specification:** [`FRONTEND_DOC.md`](file:///home/johan/Hackathons/SIH2026/ai-harness/frontend/FRONTEND_DOC.md) & [`../DOCS/FRONTEND_DOC.md`](file:///home/johan/Hackathons/SIH2026/ai-harness/DOCS/FRONTEND_DOC.md)
- **Design System & Tokens:** [`DESIGN.md`](file:///home/johan/Hackathons/SIH2026/ai-harness/frontend/DESIGN.md) & `app/globals.css`
- **Master Project Architecture:** [`../DOCS/GENERAL_PROJECT_DOC.md`](file:///home/johan/Hackathons/SIH2026/ai-harness/DOCS/GENERAL_PROJECT_DOC.md)

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
