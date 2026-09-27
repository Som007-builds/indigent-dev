"""tools/contract_check.py — G11 endpoint contract validator (Step 3).

Boots the app in-process with JOY_MODULES=stub, hits every G11 endpoint, and
validates the status code + response shape via pydantic models. Exits non-zero
on the first failure so CI catches regressions immediately.

Usage (CLI):
    python tools/contract_check.py

Usage (pytest – thin wrapper in tests/test_step3.py):
    pytest tests/test_step3.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Make sure the repo root is on sys.path so `import app` works whether the
# script is run from the repo root or from the tools/ directory.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("INFERENCE_MODE", "local")
os.environ.setdefault("JOY_MODULES", "stub")
# Unset any key that would leak Groq credentials into a test run.
os.environ.pop("GROQ_API_KEY", None)

import httpx  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402

from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Pydantic shapes for every G11 endpoint
# ---------------------------------------------------------------------------


class HealthzResponse(BaseModel):
    ok: bool


class ReadyzResponse(BaseModel):
    sqlite: str
    docker: str
    sandbox_image: str
    qdrant: str
    ollama: str


class SovereigntyResponse(BaseModel):
    inference_mode: str
    status: str
    provider: str
    network_policy: str
    internet_access: str
    sandbox_network: str
    external_api_calls: int
    external_connections: int
    external_bytes_out: int
    external_bytes_in: int
    denied_connection_attempts: int
    since: str


class ModelsResponse(BaseModel):
    active_inference_mode: str
    hardware_profile: str
    models: list[dict]
    resident_models: list[str]
    resources: dict


class TaskCreatedEvent(BaseModel):
    task_id: str
    inference_mode: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}", file=sys.stderr)
    FAILURES.append(msg)


def _ok(msg: str) -> None:
    print(f"  OK    {msg}")


def _check_status(label: str, resp: httpx.Response, expected: int) -> bool:
    if resp.status_code != expected:
        _fail(f"{label}: expected HTTP {expected}, got {resp.status_code}  body={resp.text[:200]}")
        return False
    return True


def _validate(label: str, model: type[BaseModel], data: Any) -> bool:
    try:
        model.model_validate(data)
        return True
    except ValidationError as exc:
        _fail(f"{label}: response shape mismatch — {exc}")
        return False


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Individual endpoint checks
# ---------------------------------------------------------------------------


async def check_healthz(client: httpx.AsyncClient) -> None:
    label = "GET /healthz"
    resp = await client.get("/healthz")
    if _check_status(label, resp, 200):
        if _validate(label, HealthzResponse, _json(resp)):
            if not resp.json().get("ok"):
                _fail(f"{label}: ok field is not true")
            else:
                _ok(label)


async def check_readyz(client: httpx.AsyncClient) -> None:
    label = "GET /readyz"
    resp = await client.get("/readyz")
    # Readyz may return 200 or 503 depending on which services are live;
    # both are valid responses — what matters is the shape.
    if resp.status_code not in (200, 503):
        _fail(f"{label}: unexpected status {resp.status_code}")
        return
    if _validate(label, ReadyzResponse, _json(resp)):
        _ok(label)


async def check_models(client: httpx.AsyncClient) -> None:
    label = "GET /api/models"
    resp = await client.get("/api/models")
    if _check_status(label, resp, 200):
        if _validate(label, ModelsResponse, _json(resp)):
            _ok(label)


async def check_sovereignty(client: httpx.AsyncClient) -> None:
    label = "GET /api/monitoring/sovereignty"
    resp = await client.get("/api/monitoring/sovereignty")
    if _check_status(label, resp, 200):
        if _validate(label, SovereigntyResponse, _json(resp)):
            body = _json(resp)
            # G3 invariant: local mode must never claim Groq
            if os.environ.get("INFERENCE_MODE", "local") == "local":
                if body.get("inference_mode") != "local":
                    _fail(f"{label}: inference_mode must be 'local', got {body.get('inference_mode')!r}")
                    return
                if body.get("status") == "EXTERNAL INFERENCE ACTIVE":
                    _fail(f"{label}: local mode must not claim EXTERNAL INFERENCE")
                    return
            _ok(label)


async def check_chat_sse(client: httpx.AsyncClient) -> str | None:
    """POST /api/chat — confirm 200 SSE stream with task_created event."""
    label = "POST /api/chat"
    task_id: str | None = None
    has_created = False
    async with client.stream(
        "POST",
        "/api/chat",
        json={"message": "stub:fail"},
        headers={"Accept": "text/event-stream"},
    ) as resp:
        if not _check_status(label, resp, 200):
            return None
        if "x-task-id" not in resp.headers:
            _fail(f"{label}: X-Task-Id header missing")
            return None
        task_id = resp.headers["x-task-id"]
        async for raw_line in resp.aiter_lines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            try:
                envelope = json.loads(line[len("data:"):].strip())
                if envelope.get("type") == "task_created":
                    TaskCreatedEvent.model_validate(envelope.get("data", {}))
                    has_created = True
            except Exception:
                continue
    if not has_created:
        _fail(f"{label}: no task_created event in SSE stream")
        return None
    _ok(label)
    return task_id


async def check_task_get(client: httpx.AsyncClient, task_id: str) -> None:
    label = f"GET /api/tasks/{task_id}"
    resp = await client.get(f"/api/tasks/{task_id}")
    if _check_status(label, resp, 200):
        body = _json(resp)
        required = {
            "task_id", "user_request", "current_state", "inference_mode",
            "created_at", "updated_at", "artifacts",
        }
        missing = required - set(body or {})
        if missing:
            _fail(f"{label}: missing fields {sorted(missing)}")
        else:
            _ok(label)


async def check_task_timeline(client: httpx.AsyncClient, task_id: str) -> None:
    label = f"GET /api/tasks/{task_id}/timeline"
    resp = await client.get(f"/api/tasks/{task_id}/timeline")
    if _check_status(label, resp, 200):
        body = _json(resp)
        if not isinstance(body, dict) or "entries" not in body:
            _fail(f"{label}: missing 'entries' key")
        else:
            _ok(label)


async def check_task_stream_replay(client: httpx.AsyncClient, task_id: str) -> None:
    label = f"GET /api/tasks/{task_id}/stream (replay)"
    async with client.stream("GET", f"/api/tasks/{task_id}/stream") as resp:
        if resp.status_code not in (200, 404):
            _fail(f"{label}: unexpected status {resp.status_code}")
        else:
            _ok(label)


async def check_task_approve_not_in_approval(client: httpx.AsyncClient, task_id: str) -> None:
    """Approve on a non-APPROVAL task (e.g. FAILED) must 409."""
    label = f"POST /api/tasks/{task_id}/approve (wrong state -> 409)"
    resp = await client.post(
        f"/api/tasks/{task_id}/approve",
        json={"approver": "tester", "decision": "approve"},
    )
    if resp.status_code == 409:
        _ok(label)
    else:
        _fail(f"{label}: expected 409, got {resp.status_code}")


async def check_chat_capacity(client: httpx.AsyncClient) -> None:
    """POST /api/chat with empty message -> 422."""
    label = "POST /api/chat (empty message -> 422)"
    resp = await client.post("/api/chat", json={"message": ""})
    if _check_status(label, resp, 422):
        _ok(label)


async def check_error_shape(client: httpx.AsyncClient) -> None:
    """A 404 must carry the standard error envelope."""
    label = "Error envelope shape (GET /api/tasks/nonexistent)"
    resp = await client.get("/api/tasks/does-not-exist-xyz-123")
    if not _check_status(label, resp, 404):
        return
    body = _json(resp)
    if not isinstance(body, dict) or "error" not in body:
        _fail(f"{label}: missing 'error' key in 404 body")
        return
    error = body["error"]
    for field in ("code", "message"):
        if field not in error:
            _fail(f"{label}: error missing '{field}' field")
            return
    _ok(label)


async def check_inference_mode_header(client: httpx.AsyncClient) -> None:
    """Every response must carry X-Inference-Mode."""
    label = "X-Inference-Mode header"
    resp = await client.get("/healthz")
    if "x-inference-mode" not in resp.headers:
        _fail(f"{label}: header missing on GET /healthz")
    else:
        _ok(label)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_checks() -> int:
    """Run all checks; return 0 if all pass, 1 otherwise."""
    app = create_app()
    print("=== contract_check: G11 endpoint validation ===")
    print(f"    INFERENCE_MODE={os.environ.get('INFERENCE_MODE')}  JOY_MODULES={os.environ.get('JOY_MODULES')}")

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0) as client:
            await check_healthz(client)
            await check_readyz(client)
            await check_models(client)
            await check_sovereignty(client)
            await check_inference_mode_header(client)
            await check_error_shape(client)
            await check_chat_capacity(client)

            task_id = await check_chat_sse(client)
            if task_id:
                await check_task_get(client, task_id)
                await check_task_timeline(client, task_id)
                await check_task_stream_replay(client, task_id)
                await check_task_approve_not_in_approval(client, task_id)

    if FAILURES:
        print(f"\n=== {len(FAILURES)} check(s) FAILED ===", file=sys.stderr)
        for msg in FAILURES:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    print("\n=== All checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_checks()))
