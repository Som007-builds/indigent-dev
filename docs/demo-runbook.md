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

## Commands
To verify the failure/security matrix:
```bash
# Ensure JOY_MODULES=real is set in .env or your environment
make test  # Or pytest -q tests/integration/
```
