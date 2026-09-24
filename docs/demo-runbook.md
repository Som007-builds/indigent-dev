# Offline demo runbook

This runbook is for the joint Step 10 demo. It must be run only after Joy's real
modules are merged and their `JOY_MODULES=real` wiring passes the integration
matrix. Do not demonstrate with stubs as a substitute for the real control plane.

## One-time online preparation

1. Create and activate the project virtual environment, then install the locked
   dependencies: `make setup`.
2. Pull Qdrant and build the sandbox: `docker compose pull` and
   `docker build -t indigent-sandbox:1 sandbox/`.
3. Pull every Ollama model selected by the real model registry. Record the model
   identifiers used for the demo.
4. Verify `docker compose config` shows only Qdrant and `127.0.0.1:6333:6333`.

## Offline checklist

- Disconnect the machine from external networks after preparation.
- Confirm `.env` (or exported environment) contains `INFERENCE_MODE=local` and
  `JOY_MODULES=real`; the shipped `.env.example` also defaults to local mode.
- Start Qdrant: `docker compose up -d`.
- Start Ollama locally and ensure the selected models are resident/available.
- Apply the administrator-reviewed host firewall procedure in
  [network-lockdown.md](network-lockdown.md); this repository never applies OS
  firewall changes automatically.
- Start the backend on loopback only:
  `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.

## Pre-demo verification

```powershell
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz
curl http://127.0.0.1:8000/api/monitoring/sovereignty
pytest -q -m needs_models
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

## Completion and teardown

Archive the generated outputs and audit data as required by the deployment. Stop
Qdrant with `docker compose stop` when the demo is complete. Do not remove data
volumes unless retention policy explicitly authorizes it.
