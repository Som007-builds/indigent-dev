"""The runner must not pre-empt the orchestrator's CLASSIFY step.

`TaskRunner._run` builds a `TaskContext` and hands it to the orchestrator. It used to
hardcode ``task_type="inspection"`` there, which contradicts G7 ("task_type set by
orchestrator CLASSIFY; before that null") and had a real consequence beyond the contract:
``app/policy/validator.py:30`` looks the allow-list up by ``ctx.task_type``, so
pre-seeding "inspection" applied ``ALLOWED_TOOLS["inspection"]`` to *every* task. A
coding task would be validated against the inspection tool set -- ``create_code`` and
``run_tests`` denied, ``ocr_document`` wrongly permitted.

Both orchestrators assign the type during CLASSIFY (the stub at
``app/stubs/orchestrator.py:172``, Joy's at ``app/agent/orchestrator.py:320``) before any
policy or tool call, so nulling the initial value is correct rather than merely tidy.

This is a regression guard rather than a restatement: the hardcoding arrived silently in
a merge, where it looked like intentional wiring and broke nothing loudly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import pytest

from app.config import Settings
from app.contracts.models import TaskContext
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.events import EventBus
from app.core.repo import Repository
from app.core.taskrunner import TaskRunner
from app.deps import build_services


class _RecordingOrchestrator:
    """Captures the `TaskContext` it is handed, then finishes immediately."""

    def __init__(self) -> None:
        self.seen: list[TaskContext] = []

    async def run(  # type: ignore[override]
        self, ctx: TaskContext, user_request: str, file_ids: list[str], services: object
    ) -> AsyncIterator[object]:
        self.seen.append(ctx)
        yield {"type": "completed", "data": {"final_result": "ok"}}

    async def approve(
        self, task_id: str, approver: str, decision: str, note: str | None
    ) -> None:
        return None


@pytest.fixture
async def runner(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, inference_mode="local", max_active_tasks=4)
    repo = Repository(Database(tmp_path / "db.sqlite"))
    await repo.db.initialize()
    services, _real, _, _ = build_services(settings)
    services.audit = AuditLoggerImpl(repo, settings)
    orchestrator = _RecordingOrchestrator()
    return (
        TaskRunner(repo, EventBus(repo, "local"), services, orchestrator, settings),  # type: ignore[arg-type]
        orchestrator,
        repo,
    )


@pytest.mark.asyncio
async def test_runner_does_not_preset_the_task_type(runner) -> None:
    task_runner, orchestrator, _repo = runner
    task_id = await task_runner.start("inspect the pipe", [])
    async with asyncio.timeout(5):
        while not orchestrator.seen:
            await asyncio.sleep(0.01)
    ctx = orchestrator.seen[0]
    assert ctx.task_type is None, (
        f"runner pre-set task_type={ctx.task_type!r}; CLASSIFY owns this assignment (G7)"
    )
    assert ctx.task_id == task_id
    assert ctx.workspace.is_dir()


@pytest.mark.asyncio
async def test_a_preseeded_type_would_misapply_the_allowlist(tmp_path: Path) -> None:
    """The reason the previous value was not merely wrong but dangerous.

    Pins the behaviour that made the hardcoding matter: the allow-list is keyed by task
    type, so a pre-seeded "inspection" would deny a coding task's real tools and permit
    the inspection set's tools for work that has no business running them.
    """
    from app.policy.allowlist import ALLOWED_TOOLS

    assert "create_code" in ALLOWED_TOOLS["coding"]
    assert "create_code" not in ALLOWED_TOOLS["inspection"]

    # The context the runner used to build, and the one it builds now.
    stale = TaskContext(
        task_id="t", task_type="inspection", workspace=tmp_path, inference_mode="local"
    )
    assert stale.task_type in ALLOWED_TOOLS
    assert "create_code" not in ALLOWED_TOOLS[stale.task_type]

    current = TaskContext(
        task_id="t", task_type=None, workspace=tmp_path, inference_mode="local"
    )
    # Fails closed rather than defaulting: with no classification, no tool is permitted.
    # That is the correct posture (G3), and the orchestrator assigns a real type during
    # CLASSIFY before any of this is consulted.
    assert current.task_type not in ALLOWED_TOOLS
