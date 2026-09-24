import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.repo import Repository
from app.main import create_app


async def make_repo(tmp_path) -> Repository:
    database = Database(tmp_path / "db.sqlite")
    await database.initialize()
    return Repository(database)


@pytest.mark.asyncio
async def test_schema_is_idempotent(tmp_path):
    database = Database(tmp_path / "db.sqlite")
    await database.initialize()
    await database.initialize()
    async with database.connection() as conn:
        row = await (await conn.execute("SELECT v FROM schema_version")).fetchone()
    assert row["v"] == 1


@pytest.mark.asyncio
async def test_json_fields_round_trip(tmp_path):
    repo = await make_repo(tmp_path)
    await repo.create_task("task", "request", "local")
    await repo.append_json_field("task", "errors", {"code": "EXAMPLE"})
    assert json.loads((await repo.get_task("task"))["errors"]) == [{"code": "EXAMPLE"}]


@pytest.mark.asyncio
async def test_audit_is_append_only_and_redacted(tmp_path):
    repo = await make_repo(tmp_path)
    audit = AuditLoggerImpl(repo, Settings(data_dir=tmp_path))
    await audit.emit(
        "TASK_CREATED", "test", "create", details={"api_key": "x", "message": "gsk_abc"}
    )
    entry = (await repo.list_audit())[0]
    assert entry["inference_mode"] == "local"
    assert json.loads(entry["details"]) == {"api_key": "[REDACTED]", "message": "[REDACTED]"}
    async with repo.db.connection() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            await conn.execute("UPDATE audit_log SET action='changed'")
        with pytest.raises(sqlite3.DatabaseError):
            await conn.execute("DELETE FROM audit_log")


@pytest.mark.asyncio
async def test_invalid_audit_category_rejected(tmp_path):
    repo = await make_repo(tmp_path)
    audit = AuditLoggerImpl(repo, Settings(data_dir=tmp_path))
    with pytest.raises(ValueError, match="invalid audit category"):
        await audit.emit("NOT_A_CATEGORY", "test", "bad")


@pytest.mark.asyncio
async def test_startup_recovery_marks_stuck_task_failed_and_audits(tmp_path):
    repo = await make_repo(tmp_path)
    await repo.create_task("stuck", "request", "local")
    recovered = await repo.recover_interrupted_tasks()
    for task_id in recovered:
        await AuditLoggerImpl(repo, Settings(data_dir=tmp_path)).emit(
            "TASK_FAILED", "startup", "recovered interrupted task", "error", task_id
        )
    task = await repo.get_task("stuck")
    assert task["current_state"] == "FAILED"
    assert json.loads(task["errors"])[-1]["code"] == "INTERRUPTED"
    assert (await repo.list_audit("stuck"))[0]["category"] == "TASK_FAILED"


@pytest.mark.asyncio
async def test_application_startup_recovers_stuck_tasks(tmp_path):
    repo = await make_repo(tmp_path)
    await repo.create_task("stuck", "request", "local")
    with TestClient(create_app(Settings(data_dir=tmp_path))):
        pass
    assert (await repo.get_task("stuck"))["current_state"] == "FAILED"
    assert (await repo.list_audit("stuck"))[0]["category"] == "TASK_FAILED"


@pytest.mark.asyncio
async def test_counters_increment_atomically_under_concurrency(tmp_path):
    repo = await make_repo(tmp_path)
    await asyncio.gather(*(repo.increment_counter("external_api_calls") for _ in range(50)))
    assert (await repo.get_counters())["external_api_calls"] == 50
