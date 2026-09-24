import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.events import EventBus
from app.core.repo import Repository
from app.core.taskrunner import TaskCapacityError, TaskRunner
from app.deps import build_services
from app.errors import AppError
from app.main import create_app


async def runner_for(tmp_path, **settings_values):
    settings = Settings(data_dir=tmp_path, **settings_values)
    repo = Repository(Database(tmp_path / "db.sqlite"))
    await repo.db.initialize()
    services, orchestrator, _, _ = build_services(settings)
    services.audit = AuditLoggerImpl(repo, settings)
    return TaskRunner(
        repo, EventBus(repo, settings.inference_mode), services, orchestrator, settings
    ), repo


async def wait_for_state(repo, task_id, state, timeout=3):
    async with asyncio.timeout(timeout):
        while (await repo.get_task(task_id))["current_state"] != state:
            await asyncio.sleep(0.02)


async def wait_for_runner(runner, task_id, timeout=3):
    async with asyncio.timeout(timeout):
        while task_id in runner._tasks:
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_events_replay_without_gaps_or_duplicates(tmp_path):
    _, repo = await runner_for(tmp_path)
    bus = EventBus(repo, "local")
    await repo.create_task("task", "request", "local")
    await bus.publish("task", "one", {})
    await bus.publish("task", "two", {})
    stream = bus.subscribe("task", 0)
    first = await anext(stream)
    second = await anext(stream)
    assert [first["id"], second["id"]] == [1, 2]
    await stream.aclose()


@pytest.mark.asyncio
async def test_happy_stream_orders_events_and_task_survives_unsubscribed_client(tmp_path):
    runner, repo = await runner_for(tmp_path)
    task_id = await runner.start("normal", [])
    # No subscriber remains after this point: the background task must still complete.
    await wait_for_state(repo, task_id, "APPROVAL", 3)
    await runner.approve(task_id, "reviewer", "approve", None)
    await wait_for_state(repo, task_id, "COMPLETE", 3)
    await wait_for_runner(runner, task_id)
    replay = []
    stream = runner.bus.subscribe(task_id)
    async for event in stream:
        replay.append(event)
        if event["type"] in {"completed", "failed"}:
            break
    await stream.aclose()
    assert replay[-1]["type"] == "completed"
    assert [event["type"] for event in replay] == [
        "task_created",
        "state_changed",
        "state_changed",
        "plan",
        "state_changed",
        "retrieval",
        "state_changed",
        "verification",
        "state_changed",
        "artifact_created",
        "state_changed",
        "artifact_validation",
        "approval_requested",
        "approved",
        "completed",
    ]


@pytest.mark.asyncio
async def test_failure_timeout_and_approval_are_detached(tmp_path):
    runner, repo = await runner_for(tmp_path, hard_task_timeout_s=1, approval_timeout_s=2)
    failed = await runner.start("stub:fail", [])
    await wait_for_state(repo, failed, "FAILED")
    async with asyncio.timeout(1):
        while "TASK_FAILED" not in [entry["category"] for entry in await repo.list_audit(failed)]:
            await asyncio.sleep(0.01)
    await wait_for_runner(runner, failed)
    slow = await runner.start("stub:slow", [])
    await wait_for_state(repo, slow, "FAILED", 2)
    assert json.loads((await repo.get_task(slow))["errors"])[-1]["code"] == "TASK_TIMEOUT"
    await wait_for_runner(runner, slow)
    waiting = await runner.start("normal", [])
    await wait_for_state(repo, waiting, "APPROVAL", 3)
    await asyncio.sleep(1.1)
    assert (await repo.get_task(waiting))["current_state"] == "APPROVAL"
    await runner.approve(waiting, "reviewer", "approve", None)
    await wait_for_state(repo, waiting, "COMPLETE", 3)
    await wait_for_runner(runner, waiting)


@pytest.mark.asyncio
async def test_approval_conflict_and_capacity(tmp_path):
    runner, repo = await runner_for(tmp_path, max_active_tasks=1)
    with pytest.raises(AppError) as missing:
        await runner.approve("missing", "a", "approve", None)
    assert missing.value.http_status == 404
    task = await runner.start("normal", [])
    with pytest.raises(TaskCapacityError):
        await runner.start("another", [])
    with pytest.raises(AppError) as early:
        await runner.approve(task, "a", "approve", None)
    assert early.value.http_status == 409
    await wait_for_state(repo, task, "APPROVAL", 3)
    await runner.approve(task, "a", "approve", None)
    with pytest.raises(AppError) as repeated:
        await runner.approve(task, "a", "approve", None)
    assert repeated.value.http_status == 409
    await wait_for_state(repo, task, "COMPLETE", 3)
    await wait_for_runner(runner, task)


@pytest.mark.asyncio
async def test_http_validation_and_task_shape(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, max_message_chars=20))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.post("/api/chat", json={"message": ""})).status_code == 422
            assert (await client.post("/api/chat", json={"message": "x" * 21})).status_code == 422
            response = await client.post("/api/chat", json={"message": "stub:fail"})
            assert response.status_code == 200
            task_id = response.headers["x-task-id"]
            task = (await client.get(f"/api/tasks/{task_id}")).json()
            assert task["inference_mode"] == "local"
            async with asyncio.timeout(1):
                while task_id in app.state.runner._tasks:
                    await asyncio.sleep(0.01)
            await response.aclose()
