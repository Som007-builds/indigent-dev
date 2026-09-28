# Frontend Fix Work List — `frontend/ai-harness-sih-main/`

**Created:** 2026-09-27
**Scope:** Make the frontend honest and demo-safe. It is already wired to the backend; the problem is that it fabricates data when the backend disagrees, is absent, or returns fields it didn't expect.
**Rule for this whole document:** *Never display a value the backend did not send.* Unknown is a valid state. Fabricated is not.

**Legend:** ⬜ Not started · 🟡 In progress · ✅ Done · ⛔ Blocked on someone else · ⏭️ Skipped by owner decision

---

## Progress log

| Date | Phase | Result |
|---|---|---|
| 2026-09-27 | Phase 0 | **Skipped by owner decision** — `frontend/` deliberately left untracked (a copy is held elsewhere). |
| 2026-09-27 | Phase 1 | **All 12 P0 items done** (1.1–1.12; 1.10/1.11/1.12 were discovered during implementation and added). `pnpm install` run, then `pnpm typecheck` ✅ clean, `pnpm build` ✅ 7/7 routes, `pnpm lint` 23 → **19** errors (all 19 pre-existing, none in code written for these fixes). |
| 2026-09-28 | Phase 1 | **1.13 added and done** — the Documents page fabricates a table row *and a success toast* when an upload fails, and fabricates a downloadable `.txt` file when a download fails. Found while fixing 2.2. Lint 19 → 18. |
| 2026-09-28 | Phase 2 | **2.2, 2.3, 2.4, 2.5 done.** Two new backend endpoints/behaviours landed (a `GET /api/files/{file_id}` download route; `active_model_id` round-tripping through `/api/models`), and two silent-write bugs fixed (`POST /api/models` and `POST /api/models/active` returned `{"status":"ok"}` for a discarded write). Lint 18 → **17**. `ruff check .` ✅ and `pytest -q` at **2 failed, 416 passed, 16 skipped** — the 2 failures unchanged and Docker-gated. |
| 2026-09-28 | Phase 2 | **2.1 done — Phase 2 complete.** Two P0 defects found on the way (**1.14** the API proxy delivered *zero* SSE body bytes; **1.15** a dropped connection was reported as a failed task), plus a `groq-model` fabrication the Phase 1 sweep missed. The proxy is now `app/api/[...path]/route.ts`, a streaming reverse proxy replacing the buffering `rewrites()` entry; all 19 non-SSE routes regression-tested through it. Lint 17 → **15**. `ruff check .` ✅. **`pytest -q` regressed to 5 failed, 413 passed, 16 skipped** — *not* caused by this work; root-caused below. |

**Live verification (2026-09-28).** Stub backend on `127.0.0.1:8000` (`JOY_MODULES=stub`, no Docker/Ollama/Qdrant needed) behind a production Next build on `127.0.0.1:3000`. Resume verified end-to-end through the proxy: a 13-frame log replayed as exactly `[385…390]` after a `Last-Event-Id: 384` cut — identically direct and proxied, no duplicate, no gap, cut event excluded. An earlier rewrite-based probe is preserved at `%TEMP%\opencode\probe_sse.py`.


**Toolchain note:** `node_modules` did not exist when this work started — the app had never been run in this repo. `pnpm install` completed 2026-09-27 (pnpm 10.22.0, Node v24.11.0). `node_modules/` and `.next/` are therefore now on disk inside the untracked folder.

**Lint trend:** 23 → 19 → 18 → 17 → **15** errors. All 15 pre-existing: `no-explicit-any` on backend event payloads, `set-state-in-effect` on load effects, `any` casts in the hand-drawn P&ID artwork, and `react/no-unescaped-entities` on ASCII art. Baseline recorded before any change. Item 2.1 *removed* two — the `prefer-const` and the stale `activeModelId` dependency travelled with code relocated into `applyStreamEvent`, and that code is now owned by this work rather than inherited. No new finding is in any file written for these fixes; confirmed per-file with `npx eslint . -f json`, not by eye.

---

## Summary of the problem

All 20 backend routes have a client method. ~~Transport, proxy, error-envelope parsing, and the SSE frame parser are correct.~~ The failures are in the **presentation layer**, and they cluster in the exact panels a reviewer inspects: P&ID analysis, the approval gate, citations, the sovereignty monitor, and the Models tab.

> **Correction, 2026-09-28 (item 2.1).** The sentence above originally read "Transport, proxy, error-envelope parsing, and the SSE frame parser are correct" and that was **wrong about the proxy.** The `next.config.ts` rewrite buffered every `/api/*` response, so a `text/event-stream` body was never delivered until the client disconnected — headers arrived, then nothing, indefinitely. The live event feed, the product's headline feature, was entirely dead in the browser. Error-envelope parsing and the frame parser were genuinely fine. This is recorded here because "the audit read the code and the code looked right" is precisely how it passed review: a buffering rewrite is indistinguishable from a working one unless you measure byte arrival over time. See **1.14**.


Roughly 9 of the defects below are cases where a `||` or `??` fallback substitutes a hardcoded string for a value the backend omits. Those are the highest-value fixes and the lowest-risk to make.

> **Update after Phase 1.** The original audit found 9 P0 defects. Fixing them surfaced **four more** (1.10, 1.11, 1.12, 1.13), and several of the 9 turned out to be *larger* than logged — the Models page had five independent fabrication sources rather than two, `triggerSimulatedEgress` also incremented the counter it displayed, and `handleModify` called no backend at all. The recurring shape is: **a control that has no backend behind it still renders a success state.** The `|| "Groq Cloud"` class was the visible symptom; the fictional endpoint is the deeper disease.
>
> **Update after Phase 2 items 2.2–2.5.** 1.13 is the clearest instance of that shape and the audit missed it entirely. The Documents page's download button did not 404 — it *generated a file*. Clicking Download on a real inspection PDF produced a `.txt` containing `CONFIDENTIAL AIR-GAPPED RECORD: <name> CATEGORY: … SIZE: … UPLOADED: …`, because the URL was built from the file name against a route that did not exist and the `else` branch was therefore the **normal** path. A demonstration of this product would hand a judge a fabricated deliverable and call it the document. The lesson for the remaining phases: **a `catch` or `else` block that invents data is worse than a missing feature**, because a missing feature is visible to a reviewer and an invented one is not.
>
> The same audit of the backend found two instances of the inverse defect — **real code claiming success it did not deliver.** `POST /api/models` and `POST /api/models/active` both used `if hasattr(...)` and returned `{"status": "ok"}` whether or not the handler existed, so the stub acknowledged registrations and selections it silently dropped. Fixed to return 501. A `catch` that invents data and a `hasattr` guard that invents success are the same mistake on opposite sides of the wire.

---

## Phase 0 — Preserve (do this before anything else)

| # | Task | Status | Owner |
|---|---|---|---|
| 0.1 | `git add frontend/` — the entire folder is untracked | ⏭️ Skipped by owner decision 2026-09-27 ("I have it already somewhere") | Soham |
| 0.2 | Confirm `node_modules/`, `.next/` are ignored before the first commit | ⏭️ Skipped — moot while untracked | Soham |

> **Why first:** `git ls-files` returns zero frontend files. `git status` shows only `?? frontend/`. A single `git clean -fd` or a wrong branch operation destroys the whole build. Nothing else on this list matters until this is done.

**Acceptance:** `git ls-files frontend | Measure-Object` > 0, and `git status --short` shows staged files rather than `?? frontend/`.

---

## Phase 1 — P0: stop displaying fabricated data

These are ordered by blast radius. Each is a small, local edit.

### ✅ 1.1 — Remove the P&ID fake-success fallback

**Status:** Done 2026-09-27. The 17-line `catch` fabrication is deleted. `app/pid-viewer/page.tsx` now has an `errorMessage` state and a red `role="alert"` toast that renders `describeError(err)` from the real `ApiError` (`code: message`). No code path reachable from a failed `analyzePID` touches `setDiagrams`.

**Where:** `app/pid-viewer/page.tsx:72-88`
**What:** The `catch` block fabricates a complete P&ID analysis from `pidDiagramsList[0]` (a hardcoded *C-101 crude distillation unit*) and toasts `"P&ID analysis complete! Detected N equipment tags."` Any failure — backend down, 415 unsupported type, 413 too large, 503 sandbox — presents a successful analysis of a **different drawing**.

**Do:** Delete the fabricated `newDiagram` construction. On error, set a real error state and surface the backend's `error.code` / `error.message` from `ApiError`. Never populate the diagram list on the failure path.

**Acceptance:**
- With the backend stopped, uploading a P&ID shows a visible error — not a graph.
- No code path reachable from `analyzePID` failure adds an entry to the diagrams list.
- Grep confirms `pidDiagramsList` is referenced only by the static browse list, never by the upload handler.

---

### ✅ 1.2 — Remove fabricated equipment counts

**Status:** Done 2026-09-27. The `|| 4 / || 2 / || 1 / || 3` chain is replaced by `countEquipment()`, which reads the node's declared type (`symbolType` / `symbol_type` / `type`) and returns `undefined` when **no** node carries a type field — in which case `equipmentCount` is omitted from the diagram entirely rather than filled in.

**Where:** `app/pid-viewer/page.tsx:63-66`
**What:** `|| 4`, `|| 2`, `|| 1`, `|| 3` — a genuine analysis that detects **zero** valves displays "4". The counts are shown as extraction results.

**Do:** Count from `graphData.nodes` only. Omit the field, or show `0`, when the count is zero. Do not substitute a plausible number.

**Acceptance:** Feed a response with an empty `nodes` array; the UI shows 0, not 4. Grep confirms no `|| <number>` remains in the `equipmentCount` block.

---

### ✅ 1.3 — Fix the P&ID overlay image URL

**Status:** Done 2026-09-27. Resolved via `graphData.overlay_artifact_id ?? res.artifact_ids?.[1]` → `apiClient.getArtifactDownloadUrl(...)`. The dead `/fixtures/sample_pid_scan.png` fallback is gone; when no overlay id is returned the field is omitted and the toast says *"No overlay image was returned."*

> **Correction to this item as originally written.** The plan claimed `overlay_artifact_id` was "already declared but never used" and implied it was absent from the wire. It is in fact set by `app/api/pid.py:38` (`payload["overlay_artifact_id"] = overlay_artifact.artifact_id`) and returned inside `graph`. The field was briefly deleted from `BackendPIDAnalyzeResponse` during implementation and has been restored. The plan's conclusion (use the artifact id, not `overlay_image_path`) was right; its evidence about the field was wrong.
>
> **Also learned:** with the stub pipeline, `overlay_image_path` is just the uploaded scan's own path echoed back (`app/stubs/pid.py:11`), and `_copy_contained_overlay` (`app/api/pid.py:54`) copies it to `outputs/pid-overlay.<ext>`. So `artifact_ids[1]` is a servable copy of **the source drawing**, not a generated overlay. Honest, and worth knowing before anyone describes it as a detection overlay.

**Where:** `app/pid-viewer/page.tsx:60`
**What:** `overlayImageUrl: graphData.overlay_image_path || "/fixtures/sample_pid_scan.png"`
Two separate bugs:
1. `overlay_image_path` is a **server filesystem path** (`data/pid/{file_id}/…`), not a servable URL. Used as an `<img src>` it always 404s.
2. The fallback path is also dead — there is **no `public/` directory** in this project, so `/fixtures/sample_pid_scan.png` does not exist either. (`lib/pid-data.ts:10` has the same problem with `/PnID.png`.)

**Do:** Build the URL from the overlay artifact id: `apiClient.getArtifactDownloadUrl(overlay_artifact_id)`. The frontend type `BackendPIDAnalyzeResponse.graph.overlay_artifact_id` is **already declared but never used**; the backend returns it inside `artifact_ids` (`app/api/pid.py:40` → `artifact_ids[1]`). Resolve it from there. If neither is available, render the graph without an overlay image — do not substitute a placeholder path.

**Acceptance:** With a real analysis, the overlay `<img>` loads from `/api/artifacts/{id}?download=1` and returns 200. No `img src` is ever set to a `data/…` filesystem path.

---

### ✅ 1.4 — Strip invented values from the approval gate

**Status:** Done 2026-09-27.

**Removed from the `approval_requested` handler** (`lib/workbench-context.tsx`): `measuredValue: "3.8 mm"`, `thresholdValue: "4.5 mm"`, `complianceStatus: "REJECT"`, `standardRef: "SOP-ENG-042 §4.2"`, `rationale: "Safety critical operation requires authorized managerial sign-off."`, `reviewerRoleRequired: "Senior Plant Inspection Officer"`, and the invented filenames `["approval_note.docx", "calculation_sheet.xlsx"]`.

**What it maps now:** only `summary → recommendation` and `artifact_ids → deliverablesPending`. Every other field is omitted. The pending list is relabelled **"Awaiting sign-off:"** and holds real artifact ids, not invented filenames.

**`ApprovalData`** — all fields made optional, with a comment recording that the event carries only `{artifact_ids, summary}`.

**`components/workbench/approval-gate.tsx`** — every block is now conditional: the recommendation card renders only if `recommendation` or `rationale` exists; the three-cell metrics grid renders only if at least one of the four values exists, and each cell individually; the deliverables list renders only when non-empty; the footer shows the real `approvedBy` after a decision and a neutral "Awaiting sign-off" before one (the invented "Signer: Senior Plant Inspection Officer" is gone).

**Acceptance verified:** the literals `3.8 mm`, `4.5 mm`, `SOP-ENG-042 §4.2`, `Senior Plant Inspection Officer` and `calculation_sheet.xlsx` no longer appear anywhere under `app/ components/ lib/ types/`.

---

### ✅ 1.5 — Strip invented citations

**Status:** Done 2026-09-27.

**Removed from both call sites** (`lib/workbench-context.tsx`, live stream and `loadTask`): `source || "SOP-ENG-042"`, `title || "Refinery Standard Operating Procedure"`, `section || "Section 4.2"`, `page || 1`, `confidence || 0.95` (live) / `0.96` (loadTask). Note the two paths used *different* invented confidences, so they could never have agreed.

**New shared mapper** — `lib/citations.ts`, exporting `mapChunkToCitation(chunk, index, scope)` and `mapChunksToCitations(chunks, scope)`. Both call sites now use it, so the live and reload paths cannot drift.

Mapping: `source ← chunk_id ?? document_id`, `title ← document_id ?? chunk_id`, `section`/`page`/`confidence`/`toleranceRequired` only when the chunk actually carries them. A chunk with no identifier *and* no text returns `null` and is dropped, because there is nothing to cite.

**`SOPCitation`** — `section`, `page` and `confidence` made optional. `components/context-panel/context-panel.tsx` now renders `Page N` only when `page !== undefined` and appends `· section` only when present.

**Acceptance verified:** `Refinery Standard Operating Procedure` and `Section 4.2` no longer appear as literals. A chunk without a `score` shows no confidence figure.

> **Not done (Joy's side, non-blocking).** The RAG chunk payload has no `source`, `title` or `score` field to map. The mapper is written to consume them the moment they exist, so enriching `app/rag/`'s chunk output would light up these fields with no frontend change. Until then citations show id, title, page, section and snippet only.

---

### ✅ 1.6 — Models page claims Groq Cloud while running local models

**Status:** Done 2026-09-27. The page carried **five** independent sources of invented model data, not the two originally logged.

**1. `MODEL_PRESETS`** — a four-entry list offering *"OpenAI on Groq LPU"*, *"Alibaba Cloud on Groq LPU"*, *"SDAIA on Groq LPU"*, each with `quantization: "BF16 Native LPU"`, `engineBackend: "Groq LPU Hardware Inference"`, `vramGb: 0.0` and invented tok/s figures. **Now an empty array** with a comment explaining that the authoritative list is whatever `/api/models` returns, and that a preset implies a fetch nothing in this app performs.

**2. The `/api/models` mapping** — replaced `|| "Groq Cloud"`, `|| "Native LPU"`, `|| "Groq LPU Hardware Inference"`, `|| 120`, `|| 50` with a map over the fields the backend actually sends (`id, type, tasks, provider, model_name, available, resident, memory_estimate_mb`). Also fixed **`isResident: !!m.isResident` → `rec.resident`** — the backend key is `resident`, so every model was displaying as non-resident. `vramGb` is now derived from `memory_estimate_mb`.

**3. Two hardcoded fallback registries** — `setModels(mockModelRegistry)` in both the `.then` and `.catch` of the load effect. Removed; a failed load now sets `[]` and renders a red `role="alert"` panel naming the failure. An empty list renders *"No models are registered"* rather than assuming a default.

**4. `activeModel` memo** — fell back to a literal `{name: "GPT-OSS 120B (OpenAI / Groq)", quantization: "Native LPU", engineBackend: "Groq LPU Hardware Inference", speedTokSec: 120, firstTokenMs: 85}` object. Now returns `undefined` when no models are loaded and the header reads *"No model loaded"*.

**5. The summary header** — additionally invented `paramCount || "70B"`, `"/ 64 GB Host Allocation"`, and `"GGUF Q4_K_M · 128k Context"`. All removed; absent values now render as *"Not reported by the backend"*, and the pulsing green "active" dot only pulses when a model is genuinely `resident`.

`activeDriverId` now defaults to `""` instead of `"openai/gpt-oss-120b"`, and falls back to the resident model's id when the backend omits `active_model_id` (see item 2.4 for why that key is missing).

Model card spec cells (Context / Quantization / Memory) now show `—` instead of printing `undefined` or a default.

**Acceptance:** With the backend stopped, the page shows a red error panel and zero model cards. With it running, no card or header string contains "Groq", "LPU", "70B", "Q4_K_M", "128k" or "64 GB". `grep -rni "groq" app/ components/ lib/` returns only `lib/config.ts` labelling the non-default `groq` inference mode.

**Lint:** this file went from 3 errors to 1; the remaining one (`react-hooks/set-state-in-effect` on the pre-existing `setIsLoadingModels(true)`) predates this work.

---

### ✅ 1.12 — Model register / delete / benchmark were partly fictional

> Found while fixing 1.6. Same defect class: the UI asserts backend behaviour that does not exist.

**Where:** `app/models/page.tsx`, `lib/api-client.ts`

**What:** three controls in the models page had no backend behind them.

- **Register** — `handleAddModelSubmit` only called `setModels(prev => [...])`. Nothing was persisted, yet it toasted *"Registered …"*. The model vanished on reload. Worse, it pre-filled the form with `"70B"`, `"Open Weights"`, `"/opt/models/gguf/model-70b.gguf"`, `"Q4_K_M"`, `128000`, `40.0` and submitted those as operator-supplied values. **Now calls the real `POST /api/models`** (via a new `apiClient.registerModel`), with a blank form, an in-flight state, and a `role="alert"` error on failure. The success toast names the server-applied defaults and labels them *"unverified placeholders, not measurements"*.
- **Delete** — no delete route exists in `app/api/models.py` (only `GET /models`, `POST /models`, `POST /models/active`). Removing from local state and toasting *"Model removed from local registry"* was a lie that self-healed on reload. Now explains that no delete route exists.
- **Benchmark** — no benchmark route exists. The old handler slept 800 ms in a `setTimeout` and displayed `26.4 tok/s`, `380 prompt tok/s`, `140 ms` TTFT and `"<vramGb> GB"`, followed by the green claim **"Air-gap verification passed (0 bytes outbound)"** — a verification no code performed. The dialog now states these figures are not measured, names the absence of a route, and points at the Sovereignty Monitor for real egress counters.

**✅ Backend issue found, and now FIXED** (`app/api/models.py`, Soham's side): `POST /api/models` returned `{"status": "ok"}` even when the registration was **discarded**. It guarded with `if hasattr(models_status, "add_custom_model")`, and the stub in `app/stubs/models_status.py` has no such method — so registration silently no-opped while reporting success. It also injected its own fabricated defaults into the echoed payload (`paramCount="70B"`, `speedTokSec=30.0`, `quantization="Q4_K_M"`, `contextLength=32768`), so the frontend could not distinguish "stored" from "dropped". **Both `POST /api/models` and `POST /api/models/active` now raise `AppError("MODEL_REGISTRY_UNSUPPORTED", 501, …)` when the active `ModelsStatus` lacks the method** (see item 2.4), with a test asserting the 501. The server-side pydantic defaults were left in place — they are the documented request contract — and the frontend now labels them as unverified placeholders rather than measurements.

**Acceptance:** Stopping the backend makes "Register Model" show an error and add no card. Clicking Benchmark states that no endpoint exists and shows no numbers. No numeric performance figure is rendered anywhere on the page.

---

### ✅ 1.7 — Sovereignty monitor claims air-gap while disconnected

**Status:** Done 2026-09-27. This is the most consequential item in the plan, so it is documented in full.

**Four separate defects, all fixed:**

**1. The fabricated initial state.** `useState<SovereigntyMetrics>(defaultSovereigntyMetrics)` seeded the monitor with `isAirGapped: true`, `statusText: "Local Air-Gapped"`, `localRequests: 184`, `activeFirewallRules: 42`, and a blocked packet to `104.244.42.1`. The header therefore showed a **green, pulsing AIR-GAPPED badge before any request had been made**. Initial state is now an explicit `statusKnown: false` / `statusText: "UNKNOWN"` object with zeroed counters, and the `defaultSovereigntyMetrics` export has been deleted from `lib/mock-data.ts`.

**2. Sovereignty was never reset on failure.** Both the `else` branch (health check false) and the `catch` set only `isBackendConnected(false)`, leaving the last-known values on screen — so a backend that went down kept displaying air-gapped. Both branches now also set `statusKnown: false, statusText: "UNKNOWN"`, so stale telemetry cannot be presented as current.

**3. Four fail-open defaults on the happy path** (all removed):
| Field | Was | Now |
|---|---|---|
| `statusText` | `?? "AIR-GAPPED"` | `?? "UNKNOWN"` |
| `provider` | `?? "Groq"` | omitted if absent |
| `inferenceMode` | `?? "groq"` | omitted if absent |
| `networkPolicy` | `?? "groq_endpoint_only"` | omitted if absent |

Every one of these fails toward reassuring the operator about a system that is not reporting. A missing field is now simply absent.

**4. The badge was binary.** `isAirGapped = sovereignty.isAirGapped \|\| statusText === "AIR-GAPPED"` collapsed *unknown* into *air-gapped*. `SovereigntyMetrics` gained a required `statusKnown: boolean` carrying provenance, and `SovereigntyMonitor` now renders **three** states: green pulsing AIR-GAPPED, red pulsing AIR-GAP VIOLATED, and amber **"Status Unknown"** with a tooltip explaining that the backend has not reported and this is *not* verified. Counters render `—` rather than `0`, because "not reported" is not "zero egress".

**Also fixed while in this file:** the global model badge hardcoded `activeModelId` to `"openai/gpt-oss-120b"`, so the top bar named a specific hosted model on first paint, and inferred "Coding LLM"/"Reasoning LLM" by substring-matching that id. `activeModelId` now starts `""`, the badge reads "No model" until a model is actually reported, the pulse only animates when one exists, and the substring guess is gone. The provider and inference mode from the wire are now also displayed in the telemetry strip.

**Acceptance:** with the backend stopped the bar shows amber "Status Unknown", counters show `—`, and the model badge shows "No model". The literals `104.244.42.1` and `defaultSovereigntyMetrics` no longer appear outside explanatory comments.

---

### ✅ 1.8 — Approve/reject must honour the backend response

**Status:** Done 2026-09-27. Three separate defects, one of them not in the original audit.

**1. The swallowed error.** `catch (err) { console.warn(...) }` was followed by an unconditional `currentState: "COMPLETE"` plus a step reading *"Human Sign-off Confirmed & Deliverables Published — Senior Inspection Engineer approved recommendation. Deliverables signed and archived."* A 409 therefore displayed as a successful sign-off. **Now:** on any non-2xx the task state is left completely untouched, the error is surfaced via a new `TaskState.approvalError` field, and the handler returns early.

**2. The hardcoded approver.** `"Senior Inspection Engineer"` was passed on every call, attributing a named role to a decision no such person made. G7 specifies free-text approver with no auth in scope. `handleApprove`/`handleReject` now take `(approver, note?)` from the caller, and `approval-gate.tsx` renders a real text input for it. The recorded `approvedBy` is taken from the backend's response, not assumed.

**3. `handleModify` had no backend at all** *(not in the original audit).* It set `currentState: "REPAIR"` locally and appended a step claiming the agent was *"re-evaluating tolerance parameters with modified safety margin."* Nothing re-evaluated anything. `app/api/tasks.py`'s approval endpoint accepts only `decision=approve|reject`. It now reports that no such endpoint exists and points the operator at Reject-with-a-note.

**Success path** now derives `currentState` from `res.current_state` and `approvedBy` from `res.approved_by`, both returned by `POST /api/tasks/{id}/approve`.

`components/workbench/approval-gate.tsx` renders a red `role="alert"` panel headed **"The decision was not recorded."** whenever `approvalError` is set, disables the buttons while a request is in flight, and shows `Approved/Rejected by {approvedBy}` after the fact.

**Acceptance:** Approving a task not in `APPROVAL` → red panel with `CONFLICT (HTTP 409): …`, state does not become `COMPLETE`. Verified by construction; the live check is Phase 5.

---

### ✅ 1.9 — Remove or clearly label the simulated egress event

**Status:** Done 2026-09-27. **Removed outright** — the labelling option was rejected, because a button that produces a fake security observation will be pressed during a live demo, and a label in a tooltip is not a reliable safeguard.

`triggerSimulatedEgress` fabricated a blocked packet to `api.anthropic.com:443 (160.79.104.10)` with `TCP/TLSv1.3`, process `sandbox_container_runner`, and the reason *"Container Network Policy: --network=none active. Blocked by kernel netfilter."* — then **incremented `deniedConnectionAttempts`**, so the header displayed a rising denial count that nothing had produced.

Replaced with `refreshSovereignty()`, which re-reads `/api/monitoring/sovereignty`. The "Test Shield" button now does that, is disabled when the backend is unreachable, and its tooltip states plainly that the backend exposes no endpoint that initiates a test connection, so the button cannot and does not generate one.

**Why no real "test egress" endpoint was added:** the genuine guard is `app/net/egress_guard.py`, a host-level socket patch installed at `app/main.py:58` that refuses outbound connections, increments `denied_connections` and emits `EGRESS_DENIED`. A real test would require the backend to *attempt* an outbound connection, which collides with the standing rule in AGENTS.md G3 that code and tests make zero external network calls. **Open question for Soham:** is a deliberate, expected-to-be-refused connection attempt acceptable as an explicit operator-triggered diagnostic? If yes, an additive `POST /api/monitoring/egress-test` in `app/api/monitoring.py` is the correct home for it. Not built unilaterally.

**Acceptance verified:** `api.anthropic.com` and `104.244.42.1` no longer appear in any code path, and no denied-attempt counter can increment without a backend response.

---

### ✅ 1.10 — Hardcoded C-101 schematic shown for every drawing

> **Discovered during implementation of 1.1, not present in the original audit.** Found while checking how `overlayImageUrl` is consumed. This one is worse than 1.1 because it fires on the **success** path.

**Where:** `components/pid/pid-schematic-svg.tsx`, `components/pid/pid-graph-viewer.tsx`

**What:** `PIDGraphViewer` never renders `overlayImageUrl` at all — it delegates the canvas to `PIDSchematicSVG`, which does:
```ts
fetch(`/dexpi/${drawingId}.svg`)   // no public/ dir exists -> always 404
  .catch(() => setSvgMarkup(null))
// then:
return <DistillationSchematicSVG ... />   // hardcoded C-101 crude distillation column
```
So uploading *any* P&ID produces a correct analysis, a correct node list in the inspector panel — and a main canvas showing the **same hardcoded C-101 tower** every time. `graphData.nodes` never reach the canvas. Worse, the click/hover handlers pass that hardcoded SVG's element ids into `activeGraph.nodes.find(n => n.id === id)`, so clicking canvas nodes resolves against a *different* graph.

**Do (done):** `PIDSchematicSVG` now takes a `graph` prop and resolves in strict priority order:
1. static `/dexpi/{drawingId}.svg` markup, when it genuinely exists
2. `graph.overlayImageUrl` — the real backend overlay artifact
3. real extracted geometry — renders `nodes` with usable `bbox` as SVG rects and `edges` as lines (viewBox `0 0 100 100`, matching the documented percentage bbox contract)
4. `DistillationSchematicSVG` — **only** for `drawingId === "DWG-C101-ADU"`, the one fixture that genuinely has that artwork
5. otherwise an explicit *"No vector geometry was returned for this drawing"* state, stating whether nodes were empty or merely lacked bounding boxes

`PIDGraphViewer` also no longer falls back to `pidDiagramsList[0]` when a task has no graph; it renders *"No P&ID graph is attached to this task."* (The fixture-browser mode still falls back to the first fixture, which is correct there.)

**Acceptance:** Upload a P&ID with the backend stopped → error, no graph. Upload with the backend up → the canvas shows the returned overlay or real node geometry, never C-101 unless C-101 was selected. Select a non-C-101 fixture with no overlay → the explicit empty state.

---

### ✅ 1.11 — Undeclared metadata and a false verification claim on the P&ID page

> Found alongside 1.2 while editing the same handler.

**Where:** `app/pid-viewer/page.tsx`

**What:** the upload handler also invented `standard: "ISA-5.1"`, `category: "Primary Separation"`, and a boilerplate `description` — none of which exist in the backend `PIDGraph` payload. The metric card below them went further and rendered the literal string **"Auto-OCR Verified"** in green: a claim that OCR verification occurred, which nothing in the pipeline performs or reports. The "Available Diagrams" card also counted bundled fixtures and real analyses in one number, so an upload looked like it had replaced nothing.

**Do (done):** `standard`, `category` and `description` are now left unset (and made optional on `PIDGraph`). The card shows the real standard or *"Not declared"*, and distinguishes an analysis (*"Backend returned no standard"*) from a fixture (*"Bundled fixture metadata — not verified"*). The diagram count now splits into *"N analysed · M bundled fixtures"*.

**Acceptance:** No P&ID card displays "Auto-OCR Verified" or a hardcoded standard. `grep -r "Auto-OCR Verified" app/ components/` returns nothing.

---

### ✅ 1.13 — Documents page: failed uploads and failed downloads both fabricate (NEW)

> **Found while implementing 2.2** — the fix for a broken download link exposed a fabricated-file fallback sitting behind it. This is P0-class and the original audit missed it. Recorded per the established precedent (1.10, 1.11, 1.12) rather than silently folded into 2.2.

**Where:** `app/documents/page.tsx`

**Three fabrications, plus an unreachable status column.**

**1. A failed upload was reported as a successful one.** The `catch` in the upload handler did not surface an error — it synthesised a table row per file with `status: "Local Workspace"`, `category: "User Upload"`, `uploaded: "Today at <wall clock>"`, and toasted **"Added N document(s) to local workspace."** So a 413 (file too large), a 415 (rejected type) or a dead backend all produced a table full of documents and a green confirmation. This is the identical defect to item 1.1 on the P&ID page, in a second location. Now: a red `role="alert"` panel shows the real `ApiError` code, HTTP status and message, states that **no files were stored**, and nothing is added to the table.

**2. A failed download produced a fake file.** The download handler had an `else` branch that built a `Blob` containing the text `CONFIDENTIAL AIR-GAPPED RECORD: <name>` / `CATEGORY: …` / `SIZE: …` / `UPLOADED: …` and saved it as `<name>.txt`. Because `downloadUrl` was built from the file *name* (item 2.2) and no route matched, this branch was the **normal path, not the fallback**: clicking Download on a real inspection PDF handed the user a fabricated text placeholder carrying the PDF's filename. This is the most dangerous single defect found in the whole audit — it manufactures a plausible-looking deliverable. Now: the button is disabled with a tooltip when the backend reports no download route, and there is no code path that generates file content.

**3. Every document claimed to be "Validated".** The Status column was a hardcoded `status: "Validated"` rendered with a green `Check` badge. `GET /api/files` returns no validation field of any kind. The column is removed; the row now shows the real `kind` (`upload` / `knowledge` / `pid`) and the real `created_at`.

**Also fixed:**
- The **Type** column asserted what each file *was* — `"Inspection Scan"`, `"Plant Drawing"`, `"Word Deliverable"` — from the mime type. Any PDF renders as "Inspection Scan". Replaced with the real file extension, falling back to the `mime` column.
- The **Category** column was a derived string (`Task <first 8 of task_id>` or `"Workspace Storage"`). Replaced with the real `kind` column, labelled.
- `uploaded: … : "Workspace"` — a wall-clock/word substitution when `created_at` was absent. Now `"Not reported"`.
- `loadFiles` had an empty `catch`, so a backend failure rendered as **"No documents in workspace"** — indistinguishable from a genuinely empty workspace. It now shows a red panel stating the list *could not be read* and that the stored files are unknown.
- The upload response was assigned to an unused `const res` and discarded. It is now used: the confirmation reports the number the backend says it stored, and a response reporting **zero** files is treated as a failure rather than a success.
- React `key` was `` `${doc.name}-${idx}` ``, which breaks on duplicate filenames. Now the real `file_id`.

**Acceptance:** A rejected upload adds no rows and shows the backend's error. No download produces generated content. The strings "Validated", "CONFIDENTIAL AIR-GAPPED RECORD" and "Local Workspace" no longer appear in the file.

---

### ✅ 1.14 — The API proxy silently swallowed every SSE response (NEW)

> **Found while implementing 2.1** — SSE resume cannot be tested through a transport that delivers no body, and 2.1 was un-testable until this was fixed. P0: the headline live-progress feature was entirely dead in the browser, and the original audit had recorded the proxy as correct. Full measurement in the item 2.1 write-up above.

**Where:** `frontend/ai-harness-sih-main/next.config.ts` (the `/api/:path*` rewrite), fixed by `app/api/[...path]/route.ts`

**Status:** Fixed 2026-09-28. Every `/api/*` route now goes through a streaming reverse proxy; non-SSE routes regression-tested (19 checks, all passing).

---

### ✅ 1.15 — A dropped connection was reported to the user as a failed task (NEW)

> **Found while implementing 2.1** — building the resume path required deciding what a mid-stream transport error means, and the existing answer contradicted G11. P0, because it is a fabricated task outcome: the UI asserted the work had failed when the backend was still running it.

**Where:** `lib/workbench-context.tsx`, the `catch` around `apiClient.chatStream`

**What:** Any error from the stream set `currentState: "FAILED"` and appended a red "Execution Error" step. But G11 states plainly that **a client disconnect must not cancel the task** — the backend keeps running it. A network blip, a laptop lid closing or the proxy restarting all produced a task marked failed, a failure that never happened, and — because the state was rewritten — the task became unrecoverable at exactly the moment recovery was needed.

**Now:** the two cases are separated by whether the backend ever returned a task id (`onTaskId` fires only after the response headers arrive, and it arms the resume cursor).

- **A task id exists** → the task is running server-side, so the state is left alone. The reason is recorded in a new `TaskState.streamError` and the path hands off to `resumeActiveTask`, which reattaches from the cursor. Surfaced in `components/workbench/conversation-stream.tsx` as an amber panel: *"Live updates were interrupted… This work is still running on the secure system, but updates have stopped reaching this page."* Deliberately **not** styled as an error, and worded for a plant manager — no "stream", no SSE, no event id — per the design directive against developer jargon in primary interfaces.
- **No task id** → the request never got that far (upload failed, 429, 502), so nothing is running and reporting the failure is accurate.

`streamError` is a separate field from `currentState` and from `approvalError` on purpose: "the task failed" and "we lost the connection" are different facts, and conflating them is what made the old behaviour wrong.

**Also fixed here — a fabrication the Phase 1 sweep missed.** All three `RoutingReceipt` construction sites invented a model when the backend had not sent one:

- the `model_selected` handler used `data.model_id || "groq-model"` and `data.model_name || … || "Groq Model"`, and **never read `provider`**, the one field that actually carries the sovereignty claim;
- `loadTask` used `task.model_used || "groq-model"`. `model_used` is nullable and is only set by a `model_selected` event, so on any task that failed before selecting a model — the common case — the badge rendered the literal text **"groq-model"**;
- `submitMessage` named the locally selected model *before* the orchestrator had chosen anything, which in stub mode it cannot even do (item 2.4 returns 501).

All three also asserted `isResident: true`. G9 defines `model_selected` as `{model_id, model_name, provider}` — there is no residency flag on it, and the field is read nowhere in the UI. It is now optional and unset, because absent means *not reported*, which is not the same as false. `RoutingReceipt.modelName` and `.reason` are both rendered (badge and sovereignty monitor), so these were user-visible.

Unified into **`lib/routing.ts`** so the three sites cannot drift again: `routingFromModelSelected` (now surfacing `provider` as `Selected via <provider>`), `routingFromTaskRecord`, and `pendingRouting` (`"Awaiting selection"`). When the backend reports nothing, the receipt says so rather than naming a model.

**Acceptance:** Verified by a `pathlib.rglob` walk of every `.ts`/`.tsx`/`.js`/`.jsx`/`.json`/`.md` under the app, excluding `node_modules` and `.next`: **zero** occurrences of `groq-model`, `Groq Model`, `Groq Remote LLM` or `Groq Cloud` in live code. The only remaining mentions are the doc comments in `lib/routing.ts` recording what was removed. `isResident: true` survives in 4 places in `lib/mock-data.ts` only — the scenario fixtures already marked *DEAD CODE — DO NOT IMPORT*; no live code path asserts it. Killing the connection mid-task leaves the task state intact and shows the interruption notice, then resumes.

---

## Phase 2 — P1: make the genuinely-wired features work

### ✅ 2.1 — Wire SSE resume

**Status:** Done 2026-09-28. Two P0 defects were found while doing it, because the feature could not be tested until they were fixed. Both are listed below as **1.14** and **1.15**.

#### The blocking discovery: the proxy delivered no SSE body at all

The audit's summary asserted "Transport, proxy, error-envelope parsing, and the SSE frame parser are correct." The proxy was not. Measured against a live stub backend, same request twice:

| | first byte | chunks | frame ids | spread |
|---|---|---|---|---|
| direct `127.0.0.1:8000` | 0.83 s | 16 | 13 (300–312) | 0.83 → 2.34 s, then keep-alives at 15.8 / 30.9 / 45.8 |
| through `127.0.0.1:3000` | **never** | **0** | **0** | **nothing, for 40 s** |

Headers arrived immediately and correctly (`X-Task-Id`, `X-Inference-Mode`, `content-type: text/event-stream`) — then no body byte ever followed. The body did eventually come out, but only when the client disconnected: `curl --max-time 25` received all 3331 bytes **at teardown**. So the `rewrites()` entry in `next.config.ts` buffered the entire response and flushed on close. A rewrite that buffers looks identical to a working stream to any test that only inspects the final body, which is why this was not caught by reading code.

**Fix:** `app/api/[...path]/route.ts`, a streaming reverse proxy. A filesystem route takes precedence over `rewrites()`, so this now handles all of `/api/*`. Two rules make it stream: the upstream body is never read (`upstream.body` goes straight to the `Response`), and the request sends `accept-encoding: identity` because Node's `fetch` transparently decodes a compressed body, which would make a pass-through `content-encoding` header a lie. `content-encoding` and `content-length` are dropped from the response for the same reason. `app/api/[...path]/route.ts:1-40` records the full measurement and reasoning.

The `/api/:path*` rewrite is removed and its slot carries a comment saying not to restore it, because re-adding it would change nothing (the filesystem route wins) while reading as though the bug were fixed. `/healthz` and `/readyz` stay on the rewrite: small, non-streaming, verified working.

**After the fix**, direct and proxied are indistinguishable — proxied first byte 0.46 s, 16 chunks, 13 frame ids, arrival `0.46, 0.55, 0.67, 0.79, 0.90, 1.01 …` then keep-alives at 15.4 / 30.4 / 45.4.

Because a route handler now fronts every API call, all 19 non-SSE routes were regression-tested through it rather than assumed: header fidelity on every response, every documented GET shape, a real multipart upload (sha256 echoed correctly, `download_url` present), an exact-byte download, `POST /api/pid/analyze`, the 404 envelope shape, and the 501 from item 2.4's fix. All pass. That run also live-confirms 2.2, 2.4 and 2.5 end-to-end through the proxy.

#### The resume itself

- **`lib/sse.ts`** — one `SseFrameParser` for both stream paths, plus `isTerminalEvent`. `chatStream` and `resumeStream` speak the same wire format, so two parsers would mean a resumed task silently loses an event the live path handled — and only on refresh, the one case nobody reproduces deliberately. Same reasoning as `lib/citations.ts`.
- **`apiClient.resumeStream(taskId, lastEventId, onEvent)`** — `fetch` reader, not `EventSource`. `EventSource` re-connects on its own and cannot send `Last-Event-Id` on the *initial* connection, which is the one that matters.
- **Cursor** — `{taskId, lastEventId}` in `sessionStorage`, advanced inside the shared reducer so both paths record identically, and guarded against rewinding on a replayed frame. `sessionStorage`, not `localStorage`: it survives a refresh (the case worth covering) but not a tab close, so a task cannot silently reappear hours later in a new session — which would misrepresent an append-only audit log.
- **`applyStreamEvent`** — the ~170-line inline reducer was extracted out of `submitMessage` so the live and resumed paths cannot drift. It is verbatim; only `if (!prev) return newTask` became `return prev`, because `newTask` does not exist on the resume path.

**Two strategies, and why replaying onto `loadTask` would have been wrong.** `loadTask` maps steps from the *aggregate* columns — `task.plan` and `task.tool_calls` — under its own step ids (`step-plan-${task_id}`, `step-tool-${idx}-${task_id}`), while replayed events use `step-plan-${Date.now()}`. Seeding from the snapshot and then replaying would therefore append a **second copy of every plan and tool step**. So:

- **In-memory task survived** (the stream dropped, the page did not): resume from the cursor. `Last-Event-Id` replays only greater ids, so what is already on screen is untouched. This is what the header is for, and it is now reachable because the error path hands off to it.
- **In-memory task lost** (the page reloaded): replay the whole log from id 0, which rebuilds the task exactly as a live run did.

Artifacts are the one thing replay cannot rebuild: `artifact_created` carries only `{artifact_id, artifact_type}` (G9) — no path, no verification status — so those are merged from the snapshot afterwards, through a mapper shared with `loadTask` so the two cannot disagree.

`APPROVAL` is deliberately **not** resumable. It is a pause, not an end: the runner is waiting for a human (`APPROVAL_TIMEOUT_S` is 86400 s, and `HARD_TASK_TIMEOUT_S` explicitly excludes time in `APPROVAL`, G6), so there is nothing to replay and a stream would sit idle.

**Verified live** (stub backend, through the proxy): 13-frame log, ids strictly ascending. Resume after id 384 replayed exactly `[385…390]` — identically direct and proxied, no duplicate, no gap, the cut event not re-sent. Resuming from the final id yields no events. An unknown `task_id` returns 404 rather than a silent empty stream.

---

### ✅ 2.2 — Document download is broken for every file

**Status:** Done 2026-09-28, both sides.

**Backend (`app/api/files.py`, Soham's side) — new additive route `GET /api/files/{file_id}`.** No such route existed; only the list and the upload. `?download=1` streams the bytes, and without the flag it returns metadata, exactly mirroring `GET /api/artifacts/{id}`. An unknown id returns the standard `NOT_FOUND` envelope with a `request_id`, not a 500.

**Integrity is re-checked before the bytes are served.** The sha256 recorded at upload is recomputed and compared; a file replaced or truncated on disk returns `FILE_CORRUPT` rather than being served under the digest it was registered with. The plan suggested a magic-byte check, which would be redundant here — the file was magic-byte-validated on the way *in* (`_validate_magic`, `app/core/files.py:22`) and the sha256 comparison is strictly stronger than re-reading 16 header bytes, since it covers the whole file.

**One deviation from the plan, deliberate: `safe_join` is not used for the stored path.** `save_upload` records `stored_path=str(destination)`, which is **absolute** (`app/core/files.py:74`), and `safe_join` rejects absolute paths by design — it is built for untrusted *relative* input, so passing it a path from our own database would have failed 100% of the time. The same invariant is enforced by `_resolve_stored_file`: resolve, then require containment under `DATA_DIR`, and refuse any path with `..` or that reaches outside. Documented in `docs/decisions.md`.

**`download_url` is now emitted** by both `GET /api/files` and `POST /api/files/upload`, keyed by `file_id` and never by name.

**Frontend.** `BackendUploadedFile` gained optional `created_at`, `task_id` and `download_url` — the interface declared none of them, which is *why* the page fell back to building a URL from the file name. The download link is now built from the id alone.

**8 backend tests added** (`tests/test_files_download.py`): happy path byte-for-byte, metadata without bytes, unknown id, a row pointing at a file that was deleted, bytes changed on disk, containment, and the audit row.

**Acceptance:** met on the backend and provable without a live stack — the route is covered by tests. Live confirmation of the browser download is DoD 4.

---

### ✅ 2.3 — Audit log "Actor" column is 100% fabricated

**Status:** Done 2026-09-27. The root cause was in the type, not just the component.

**`types/workbench.ts` — `BackendAuditItem` declared three fields that do not exist.** It had `seq`, `event_type` and `actor`. The `audit_log` table (`app/core/schema.sql:8-9`, G10) has exactly `id, task_id, ts, inference_mode, category, component, action, status, details` — `seq` belongs to `task_events`, a *different* table. Because the phantom fields were typed as present, the component read them, received `undefined`, and substituted invented stand-ins. The interface is now the real schema, with required-ness following the NOT NULL constraints (`id`, `ts`, `inference_mode`, `category`, `component`, `action`, `status` required; `task_id` and `details` optional).

**`app/audit/page.tsx` — four fabrications removed:**

| Was | Now |
|---|---|
| `actor: item.actor \|\| "Orchestrator"` | two real columns: `component` **and** `category` |
| `action: item.action \|\| item.event_type \|\| "State Transition"` | `action` (NOT NULL) |
| `id: \`LOG-${item.seq \|\| idx + 1000}\`` | `id: String(item.id)` — the real autoincrement key |
| `timestamp: item.ts ? … : new Date().toLocaleTimeString()` | `item.ts` (NOT NULL) — no wall-clock substitution |

Every row in the table previously displayed the literal string **"Orchestrator"** as its actor, while the two genuine attribution columns went unread.

**Dead status styling.** The mapping was `ok → "Completed"`, `error|blocked → "Blocked"`, else `"Pending"`. The backend never writes `"blocked"` — verified against every `audit.emit` call site in `app/core/taskrunner.py`, `app/core/artifacts.py`, `app/net/sovereignty.py` and `app/agent/inference.py`, which write only `ok`, `error`, `denied` and the `info` default (`app/core/audit.py:38`). So the red treatment was unreachable, and a genuine **`denied`** — emitted by `app/net/sovereignty.py` when a model/provider violates the inference-mode policy — fell through to a green/amber **"Pending"**. The new `StatusBadge` styles `error|denied` red, `ok` green, `info` amber, and renders an unrecognised value verbatim rather than coercing it.

**`inference_mode` is now displayed.** It is a NOT NULL column that the frontend never read. On an air-gapped product this is the most audit-relevant field in the table — it records which inference mode produced each row — and it was invisible.

**Swallowed error fixed.** `catch {}` left `entries` empty, so a backend failure was visually identical to a genuinely empty ledger. It now renders a distinct red panel stating the log *could not be read* and that its contents are unknown — the opposite of implying a clean audit trail.

**Also (from the "Also" note):** `BackendTimelineResponse.task_id` is now optional, because `GET /api/tasks/timeline/all` (`app/api/tasks.py:29`) returns `{"entries": […]}` with no `task_id`.

**Acceptance:** for a real task the table shows the real `component`, `category`, `inference_mode` and `status` values. The string "Orchestrator" appears nowhere in the codebase, and cannot appear unless it came from the database.

---

### ✅ 2.4 — Model switcher never syncs with the backend

**Status:** Done 2026-09-27/28 — parts 1 and 2 complete, part 3 is Joy's.

**1. Frontend — done (with 1.7).** `activeModelId` now starts `""` instead of `"openai/gpt-oss-120b"`, and the global header badge reads **"No model"** until a model is genuinely reported. The old default was an OpenAI model id in an air-gapped product, and because the backend never overrode it, that string is very likely what the UI actually displayed.

**2. Backend stub — done.** `app/stubs/models_status.py` had no `active_model_id` and no `set_active_model`, while `app/api/models.py:35` acknowledged the id it was handed — so the selection could never survive a reload. The stub now emits `active_model_id` (emitted **unconditionally**, `null` until a selection is made, so "nothing selected yet" stays distinguishable from "this build does not report a selection") and implements `set_active_model` to record the request. Because the stub has no registry, the value is explicitly a *record of a request*, not a claim that a model is loaded: it still reports `models: []` and `resident_models: []` after a selection, and a test asserts exactly that.

**3. Backend, real implementation — Joy's, not touched.** Joy's real `ModelsStatus.status()` must also emit `active_model_id` and implement `set_active_model`. Until then the switcher will round-trip in stub mode only. **Tracked with Joy.**

**Bonus fix, same root cause.** Both `POST /api/models/active` and `POST /api/models` used `if hasattr(models_status, ...)` and returned `{"status": "ok"}` either way — acknowledging a write the backend had just discarded. Both now raise `AppError("MODEL_REGISTRY_UNSUPPORTED", 501, …)` when the method is absent, and the `hasattr` guard was moved **outside** the `try` so the following `except Exception` cannot swallow it. This also closes the backend bug reported under item 1.12.

**Tests added** (`tests/integration/test_inference_mode_reporting.py`): the stub reports `null` before any selection; a selection round-trips through `set_active_model`/`status()`; the selection round-trips through the HTTP API (`POST` then `GET`); and an unstorable registration returns 501 with `MODEL_REGISTRY_UNSUPPORTED`. The existing exact-shape assertion was extended to include the new key rather than loosened.

**Acceptance:** switching a model and reloading now shows the selection. Nothing renders an `openai/*` or `groq/*` id while `INFERENCE_MODE=local`.

---

### ✅ 2.5 — Use the `X-Inference-Mode` header the backend already sends

**Status:** Done 2026-09-27.

**Verified first:** `app/main.py:116` sets `response.headers["X-Inference-Mode"] = settings.inference_mode` inside the HTTP middleware, so it is present on **every** response including errors. `tests/test_step0.py:15`, `tests/integration/test_inference_mode_reporting.py:54`, `tests/integration/test_real_composition.py:405` and `tests/integration/test_step10_matrix.py:1015` all assert it. The header is the one mode value the backend states unconditionally, needing no second request to corroborate.

**`lib/api-client.ts`** — added a module-level `reportedInferenceMode` and an exported `getReportedInferenceMode()`, fed by `observeInferenceMode(res)`. It is called from all four response paths, including the three that bypass `handleResponse`: `checkHealth()`, `checkReady()` and the SSE success branch of `chatStream()`. It runs *before* the `res.ok` check, so a failed call still records the mode. Any value that is not exactly `local` or `groq` is ignored rather than stored.

**`lib/workbench-context.tsx`** — mode is now taken from the header first, falling back to the snapshot, and **only ever** to one of those two. The three Groq fallbacks are gone: they failed *open* (`?? "groq"`, `?? "groq_endpoint_only"`, `?? "Groq"`), i.e. an incomplete response made the product claim it was calling a hosted API. A missing field is now simply absent, which is the same direction as the `?? "AIR-GAPPED"` in the same object literal — **the inconsistency noted in the original audit is resolved**, and all fields now fail the same way.

**Disagreement is surfaced, not resolved.** `tests/integration/test_inference_mode_reporting.py` asserts the header, `/api/models` and `/api/monitoring/sovereignty` agree. If the header and the sovereignty snapshot ever disagree, a new `SovereigntyMetrics.modeConflict` is set and the monitor renders an amber **"Mode mismatch"** marker with the two values in its tooltip. Silently preferring one source would hide a real backend inconsistency.

**Also removed** two pre-existing unused imports (`CheckCircle2`, `ShieldAlert`) in `sovereignty-monitor.tsx`; that file is now lint-clean.

**Acceptance:** mode originates from the header; with the backend stopped the header is absent and mode renders as absent, never as `groq`.

---

## Phase 3 — Contract alignment

| # | Task | Where | Status |
|---|---|---|---|
| 3.1 | `TaskType` includes `'general'` and `'sovereignty_proof'`, absent from the G7 enum (`inspection`, `coding`, `pid_analysis`). Remove them and drop the `as any` cast at `workbench-context.tsx:229`. | `types/workbench.ts` | ⬜ |
| 3.2 | `fileSizeFormatted: "Validated deliverable"` — a string in a size field, set twice (`workbench-context.tsx:219`, `:530`). The backend has real sizes; use them or omit. | `lib/workbench-context.tsx` | ⬜ |
| 3.3 | `CORS_ORIGINS` defaults to `http://localhost:5173`; this app dev-serves on **:3000**. Currently masked by the same-origin rewrite, breaks the moment anyone points the browser straight at the backend. Add `:3000` or document why not. | `app/config.py` | ⬜ |
| 3.4 | No `.env.example` documenting `BACKEND_URL`. Add one next to the existing root `.env.example`. | `frontend/ai-harness-sih-main/` | ⬜ |
| 3.5 | `getArtifactDownloadUrl` returns a relative URL; fine behind the proxy, breaks under a direct backend origin. Confirm intent and comment it. | `lib/api-client.ts:215` | ⬜ |

---

## Phase 4 — Hygiene

| # | Task | Where | Status |
|---|---|---|---|
| 4.1 | `shadcn: ^4.19.0` is a **CLI** sitting in `dependencies`. Move to `devDependencies` — it currently installs into the client dependency path. | `package.json:25` | ⬜ |
| 4.2 | Three icon libraries installed: `@hugeicons/core-free-icons`, `@hugeicons/react`, `lucide-react`. Pick one. | `package.json` | ⬜ |
| 4.3 | The bundled `AGENTS.md` points at dead absolute Linux paths (`file:///home/johan/Hackathons/SIH2026/ai-harness/…`) and at `../AGENTS.md` / `../DOCS/`, none of which exist in this repo. Rewrite the links as repo-relative. | `frontend/ai-harness-sih-main/AGENTS.md` | ⬜ |
| 4.4 | `.agents/skills/**` (AI agent instruction files, ~30 files) ship inside the product folder. Confirm they belong in the repo and not in a build artifact. | `frontend/ai-harness-sih-main/.agents/` | ⬜ |
| 4.5 | `FRONTEND_DOC.md:274,281` lists "Mock API & SSE Provider" as step 1 and "Real Backend Integration" as step 8. The build shipped real calls but kept the mock fallbacks — that inconsistency is the root cause of most of Phase 1. Update the phase status to reflect reality. | `FRONTEND_DOC.md` | ⬜ |

---

## Phase 5 — Bring-up and live verification

Nothing in Phases 1–4 can be proven correct without a running stack. `node_modules` is **absent**, so the app has never run in this repo.

| # | Task | Command | Status |
|---|---|---|---|
| 5.1 | Install dependencies | `pnpm install` | ⬜ |
| 5.2 | Type check | `pnpm typecheck` | ⬜ |
| 5.3 | Lint | `pnpm lint` | ⬜ |
| 5.4 | Production build | `pnpm build` | ⬜ |
| 5.5 | Boot backend + frontend, confirm the proxy resolves | `uvicorn app.main:app --host 127.0.0.1 --port 8000` then `pnpm dev` | ⬜ |

**Then verify live — these four cannot be proven statically:**

1. **SSE survives the Next.js rewrite proxy.** `next.config.ts` proxies `/api/:path*`, and `POST /api/chat` returns `text/event-stream`. Confirm events actually arrive incrementally rather than being buffered until the stream closes. If buffered, the rewrite must be replaced with a route handler.
2. **The `X-Task-Id` response header survives the proxy.** `api-client.ts:271` depends on it; if the proxy drops it, `onTaskId` never fires and the frontend keeps its temporary `task-${Date.now()}` id.
3. **SSE frame `id` values increment** so `Last-Event-ID` resume (2.1) can work.
4. **Upload → render round-trip** for a real `.pdf` and a real P&ID image, with a stub orchestrator.

---

## Phase 6 — Documentation

| # | Task | Where | Status |
|---|---|---|---|
| 6.1 | Record the "never display an unsent value" rule in the root `AGENTS.md` and in `docs/decisions.md`, so this class of defect does not return | `AGENTS.md`, `docs/decisions.md` | ⬜ |
| 6.2 | Note in `docs/contract-mismatches.md` the frontend-side contract drift found here (audit `actor`, `isResident` vs `resident`, `overlay_image_path` vs a servable URL, missing `GET /api/files/{id}`, missing `active_model_id`) | `docs/contract-mismatches.md` | ⬜ |
| 6.3 | Update `Progress.md` Step 3, which currently records frontend contract reconciliation as complete | `Progress.md` | ⬜ |

---

## Ownership map

| Item | Owner | Note |
|---|---|---|
| 0, 1, 2.1, 2.3, 2.5, 3, 4, 5, 6 | **Soham** (platform) | All frontend, plus the backend endpoints named in 2.2 / 2.4 |
| 2.2 `GET /api/files/{file_id}` | **Soham** | Additive backend endpoint, `app/api/files.py` |
| 2.4 `active_model_id` in the real `ModelsStatus.status()` | **Joy** | Stub is Soham's to fix; the real implementation is Joy's |
| `retrieval` chunk fields (`source`, `title`, `score`) | **Joy** | RAG. Frontend fix in 1.5 removes the fabrication regardless; the richer fields are a Joy enhancement, not a blocker |

---

## Do not do

- **Do not add a mock/demo toggle** as a "fix". The fallbacks must be deleted, not made switchable. A mode flag guarantees someone enables it during a live demo.
- **Do not wire `pidDiagramsList` or `mockModelRegistry` into a live code path.** They may stay as static browse fixtures, clearly labelled.
- **Do not add `GET /api/tasks` SSE polling as a substitute for 2.1** — the backend already ships gapless replay; use it.
- **Do not change `app/providers/`, `app/agent/`, `app/policy/`, `app/rag/`, `app/artifact_validation/`** to make the frontend work. Report the mismatch instead.
- **Do not regenerate `requirements.lock`** as part of this work. The Python-version decision (3.14 vs 3.11) is still open, and `CVE-2026-48817` affects `starlette <= 1.1.0`, so re-pinning to the installed set is a regression.

---

## Definition of done

1. ~~`git ls-files frontend` is non-empty and the tree is clean.~~ **N/A — waived by owner decision 2026-09-27.** `frontend/` is deliberately untracked; a copy is held elsewhere. Every other item below is therefore uncommitted by design.
2. No UI surface displays a value absent from the corresponding backend response. Verified by stopping the backend and confirming nothing renders a plausible-looking value. **Met for Phase 1** — a code-wide scan of all 42 `.ts`/`.tsx` files under `app/ components/ lib/ types/` found zero live fabrications; the only remaining hits are explanatory comments, the quarantined dead fixtures in `lib/mock-data.ts`, and user-facing input hints. Live confirmation is DoD 4.
3. `pnpm typecheck` ✅ and `pnpm build` ✅ pass. ~~`pnpm lint` passes~~ — **adjusted:** lint holds at **15 errors, all pre-existing** (down from a 23-error baseline). The remaining 15 are `no-explicit-any` on backend event payloads, `react-hooks/set-state-in-effect` on load effects, `react/no-unescaped-entities` on the ASCII-art P&ID components, in files this work did not rewrite. Verified per-file with `npx eslint . -f json`. Raising that to zero is Phase 4.
4. SSE verified live through the proxy, including `X-Task-Id` and incremental delivery. **Met 2026-09-28** — see item 2.1. First byte at 0.46 s through the proxy against 0.83 s direct, 13 frame ids, arrival spread 0.46 → 1.81 s then keep-alives on the backend's `ping=15`. **This required replacing the buffering rewrite** (item 1.14); the proxy as originally written delivered zero body bytes, so this DoD could not be met before that fix. `X-Task-Id` and `X-Inference-Mode` both survive the new route handler.
5. An approve request the backend rejects renders an error, not a success. **Met by construction (1.8)** — on any non-2xx the task state is untouched and a red panel shows the real `code`/`status`/`message`. Live confirmation: the 409/404 envelopes returned through the new proxy match the expected shape.
6. A P&ID upload that fails renders an error, not a graph. **Met by construction (1.1)** — the 17-line `catch` that fabricated a four-node graph is gone; failures set `errorMessage` and no failure path touches `setDiagrams`. Live confirmation: `POST /api/pid/analyze` through the new proxy returns the real graph keys.
7. With `INFERENCE_MODE=local`, nothing in the UI names Groq, OpenAI, or any external provider. **Met** — the four Groq-branded preset models, the `activeModel` GPT-OSS/Groq fallback, and the `?? "Groq Cloud"` / `?? "groq"` / `?? "groq_endpoint_only"` fail-open defaults are all removed. A second round was needed in item 1.15: all three `RoutingReceipt` sites fell back to `"groq-model"`, which rendered as the badge text on any task that failed before selecting a model. Live check: `GET /api/monitoring/sovereignty` through the proxy reports `AIR-GAPPED` with `status` intact. Remaining mentions are (a) `lib/config.ts` labelling the non-default `groq` inference mode, (b) the two quarantined dead exports in `lib/mock-data.ts`, (c) comments recording what was deleted.
8. Backend gates unaffected: `ruff check .` ✅ (clean). `pytest -q` **NOT met — regressed by an incoming merge, see "Still open" below.** Baseline before that merge was 2 failed, 416 passed, 16 skipped; it is now **5 failed, 413 passed, 16 skipped**.

### Still open

- **DoD 1** — waived, not met (`frontend/` deliberately untracked).
- **DoD 3** — lint is not zero; 15 pre-existing errors, deferred to Phase 4.
- **`pytest -q` regressed: 5 failed, not 2 — root-caused, NOT fixed, and NOT this work's to fix.** `HEAD` moved under this work: a `git pull origin main` fast-forwarded `6f9aeb8 → 900fcae`, landing Joy's `feat/joy-control-plane`. `ruff check .` is still clean, and none of the files this work touched were in the incoming set, but three orchestrator timing tests now fail:

  - `tests/test_orchestrator.py::test_task_timeout` — `KeyError: 'error'`
  - `tests/integration/test_orchestrator_approval_timeout.py::test_execution_overrun_still_times_out`
  - `tests/integration/test_orchestrator_approval_timeout.py::test_execution_budget_is_still_enforced_after_approval`

  Isolated by experiment, not inference, using throwaway worktrees:

  | tree | result |
  |---|---|
  | `6f9aeb8` (pre-merge) | **3 passed in 1.80 s** |
  | `900fcae` (post-merge) | **3 failed in 38.91 s** |
  | `900fcae` + `app/deps.py` hunk reverted | 3 failed in 39.41 s |
  | `900fcae` + `app/core/taskrunner.py` reverted | 3 failed in 38.79 s |
  | `900fcae` + **`app/agent/router.py` reverted** | **3 passed in 1.05 s** |

  **Cause: `app/agent/router.py:41-42`**, added by `da6d510`, calls `self.resources.sync_ollama_residency(self.settings.ollama_base_url)` on *every* model selection — inside the orchestrator's hot path. `sync_ollama_residency` (`app/agent/resource_manager.py:118`) is a **blocking synchronous `httpx.Client.get("/api/ps")` with `timeout=5.0`**, wrapped in a bare `except` that swallows the failure. With Ollama not running, every router call burns the full 5 s and continues with stale residency. The tests encode sub-second budgets (0.05 s / 0.15 s) against a 5 s tool delay, so the stall changes what the timeout path does — hence "completed" where `TASK_TIMEOUT` was expected. The 38.9 s → 1.05 s collapse is the stall itself, not a coincidence.

  **Not fixed here, deliberately: `app/agent/` is Joy's directory (AGENTS.md G2).** Reported instead. The one-line fix is to drop the sync from the router's selection path, or to give it a cached/short-circuit path when `ollama_base_url` is already known-unreachable.

  **Two related things the owner should know:**
  1. **The same pattern is in Soham's own `app/deps.py:767`** — `_ConfiguredModelsStatus.status()` calls the same blocking sync on every call. That object is only built at `deps.py:374` inside `build_real_services`, so it does **not** affect stub mode (which is why the live proxy probe stayed fast) but in **real** mode it will make every `GET /api/models` stall up to 5 s with Ollama down — and the Models page and the workbench both poll that route. This file is Soham's to change, but the line arrived in the same merge as Joy's feature, so it has not been reverted unilaterally.
  2. **`app/core/taskrunner.py:76` was also changed by the same merge**, from `task_type=None` to `task_type="inspection"`. That contradicts G7 ("task_type set by orchestrator CLASSIFY; before that null") and, because `ALLOWED_TOOLS` is keyed by task type, a `coding` or `pid_analysis` task would be handed the *inspection* tool set — no `execute_code`, no `run_tests`. Reverting it alone did **not** fix the three tests, so it is a separate issue, but it looks like an unintended conflict resolution in a Soham-owned file and is worth a look.
- **A task at `APPROVAL` holds the client open indefinitely — found while testing 2.1, deliberately not fixed (it is not a transport issue).** Verified: the stub reaches `approval_requested` and the stream then produces nothing for as long as the approval window lasts. This is **correct backend behaviour**, not a bug — G6 sets `APPROVAL_TIMEOUT_S` to 86400 s and states that `HARD_TASK_TIMEOUT_S` *excludes* time in `APPROVAL`, so a 100 s observation is far too short to see a terminal event. Measured 105 s, 13 frames, no terminal event, server did not close. The consequence is on the client: `chatStream` from `POST /api/chat` never returns, so `submitMessage`'s `finally` never runs, `isExecuting` stays `true`, the composer stays disabled, and `refreshRecentTasks()` is never called — a user cannot start a second task while one is awaiting a human. Two viable fixes, both deferred: stop the reader at `approval_requested` and re-resume from the cursor on approve (the 2.1 machinery already supports this, and `taskrunner.approve` does publish further events on the same bus), or simply treat `APPROVAL` as not-executing. The first is more correct but changes what the live stream promises. **Worth scheduling; not started.**
- **One design question for Soham:** should an operator-triggered egress test endpoint exist? See item 1.9. Asked twice, unanswered.
- **Re-pinned question, still Joy's or the user's:** the `requirements.lock` Python version.

