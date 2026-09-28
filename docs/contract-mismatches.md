# Contract mismatches found during frontend remediation

Living document. Each row is a place where the frontend's expectation and the
backend's contract diverged, what the fix was (if any), and whether it is closed.
Created 2026-09-28 during Phases 1-6 of `frontend/Frontend-fix.md`.

Status legend: `closed` (fixed on the platform side), `joy` (fixed only on the stub;
the real implementation is Joy's), `open` (nothing to fix without a decision).

| # | Mismatch | Where the truth lives | What the frontend assumed | Fix | Status |
|---|---|---|---|---|---|
| 1 | Audit rows carry `actor`, but the audit API exposes no such field | G10 `audit_log` columns: `id, task_id, ts, inference_mode, category, component, action, status, details` | Timeline UI expected an `actor` attribute on each entry | Frontend reads the row's real fields; no invented actor | `closed` |
| 2 | `isResident` vs `resident` | G8 `ModelsStatus.status()` emits `resident_models: [str]` and per-model `resident`; there is no `isResident` anywhere in the backend | `RoutingReceipt` asserted `isResident: true` at all three construction sites | `RoutingReceipt.isResident` is now optional and unset (absent = not reported); sites unified in `lib/routing.ts` | `closed` |
| 3 | `overlay_image_path` is a server-local filesystem path, not a servable URL | G8 `PIDGraph.overlay_image_path: str`, populated by the stub with `C:\...\data\pid\...` (absolute path on the operator's machine) | P&ID viewer would have to load that path as a URL | Backend also returns `overlay_artifact_id`; the viewer must serve the overlay via the artifact download endpoint, never the raw path. The stub's echo path is honest but unservable, so a browser render requires Joy's real pipeline to populate a real artifact | `open` |
| 4 | No `GET /api/files/{file_id}` route existed | G11 lists the files surface as `POST /api/files/upload` only | Frontend fell back to `/api/files/{name}`, which matched nothing -> every document download 404'd | Route added additively (`?download=1` serves bytes after re-hashing); `download_url` emitted on upload and list | `closed` |
| 5 | No `active_model_id` in `/api/models` | G8 `ModelsStatus.status()` shape has no active model id | Model switcher fell back to hardcoded `"openai/gpt-oss-120b"` after reload | Stub now emits `active_model_id` (null until selection) and implements `set_active_model`. The real implementation is Joy's | `joy` |
| 6 | `ArtifactManifest` (G8) has no size field, so the UI's size column had nothing real to show | G8/G10: no `size_bytes` on artifacts at all | Rendered the literal string "Validated deliverable" in the size field | `annotate_size()` stats at read time; additive `size_bytes` (None = not reported) on `GET /api/tasks/{id}` and `GET /api/artifacts/{id}` | `closed` |
| 7 | Task type contract drift | G7: exactly `inspection, coding, pid_analysis`; task_type is set by CLASSIFY and null before that | Frontend typed `'general'` and `'sovereignty_proof'`; the runner pre-seeded `"inspection"` for every task | Frontend `TaskType` narrowed to the three; `taskType: TaskType \| null`. Runner pre-seed reverted to `null` (decisions.md 2026-09-28) | `closed` |
| 8 | `fileType` union in the frontend excluded types the backend can produce | G8 `ArtifactManifest.artifact_type` includes `code_package` and `pid_overlay` | UI cast artifacts into a union of a few display types | `ArtifactDeliverable.fileType` widened to the full union; no cast | `closed` |