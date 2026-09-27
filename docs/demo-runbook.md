# Indigent Demo Runbook

## Offline Checklist
- [ ] Pre-pull all required Docker images (e.g., sandbox image `indigent-sandbox:1`, Qdrant).
- [ ] Pre-pull all required Ollama models locally.
- [ ] Ensure `INFERENCE_MODE=local` is set in `.env`.
- [ ] Disconnect the host machine from the internet.
- [ ] Start backend infrastructure: `docker compose up -d` (for Qdrant).
- [ ] Start the API server: `make run` (or `uvicorn app.main:app --host 127.0.0.1 --port 8000`).

## Expected Sovereignty Output
When running in `local` mode, calling `GET /api/monitoring/sovereignty` must return:
```json
{
  "inference_mode": "local",
  "status": "AIR-GAPPED",
  "provider": "ollama",
  "network_policy": "deny_all",
  "internet_access": "BLOCKED",
  "sandbox_network": "disabled",
  "external_api_calls": 0,
  "external_connections": 0,
  "external_bytes_out": 0,
  "external_bytes_in": 0,
  "denied_connection_attempts": 0,
  "since": "<timestamp>"
}
```

The local sovereignty response must contain `"inference_mode":"local"`,
`"status":"AIR-GAPPED"`, `"provider":"ollama"`,
`"internet_access":"BLOCKED"`, `"sandbox_network":"disabled"`, and zero
for all external-call, external-connection, and byte counters. Any nonzero
external counter changes the local status to `AIR-GAP VIOLATED`: stop the demo.

## Demo execution

1. Run Demo A: a local inspection task using approved source evidence; inspect
   the task stream, artifact, and audit timeline.
2. Run Demo B: the approved coding task; show Docker sandbox execution and that
   its network is disabled.
3. Run Demo C: the P&ID workflow; show the graph/overlay artifacts and evidence.
4. For every task, verify the audit timeline contains the selected model, policy
   decision, tool result, verification/validation, approval, and completion or
   failure events as applicable; every audit row must have `inference_mode`.

## Known capability gaps on this deployment

These are real, verified limitations, not test gaps. Each fails closed with an explicit
error and an audit record; none of them is ever substituted with fabricated output.

**Demo C (P&ID) cannot complete without a local vision model.** No provisioned model
accepts images, so `/api/pid/analyze` returns `500 PID_FAILED` and the `analyze_image`
and `extract_pid_graph` tools fail closed. To close this, provision a local vision model
and re-verify; the router already requests `requires_images=True`, so nothing else
changes.

**`ocr_document` extracts the text layer first, then falls back to real local OCR.** A PDF
with no text layer is passed to Tesseract via `LocalDocumentExtractor` ->
`LocalPDFTextExtractor` -> `OCRAdapter`, and OCR works today: no code change is needed,
only the `tesseract` binary installed on the host. The adapter probes the binary once at
startup, so restart the service after installing it. A page that yields no text through
either path fails closed with `OCR_UNAVAILABLE` and the error names that remedy. Images are
not accepted by this tool at all (`_DOCUMENT_SUFFIXES` is text and PDF only). Do not add a
cloud OCR service: it would break the air gap.

**Only the 27B generation model fits, and only once.** It holds about 19.4 GB of unified
memory. While it is resident, `/api/models` reports roughly 1 GB free and
`ResourceManager` refuses to admit it again, which is the correct fail-closed behavior.
Release it before starting a task that must load it:

    curl -s http://localhost:11434/api/generate \
      -d '{"model":"qwen3.8-27b-abliterated:latest","prompt":"","keep_alive":0}'

Docker Desktop and the resident model do not coexist comfortably on this host. Unload the
model before anything that needs the Docker VM.

## Commands

To verify the failure/security matrix:
```bash
# Ensure JOY_MODULES=real is set in .env or your environment
make test  # Or pytest -q tests/integration/
```

## Completion and teardown

Archive the generated outputs and audit data as required by the deployment. Stop
Qdrant with `docker compose stop` when the demo is complete. Do not remove data
volumes unless retention policy explicitly authorizes it.
