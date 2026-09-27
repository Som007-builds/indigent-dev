import asyncio
import json
import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.contracts.interfaces import Orchestrator, Services
from app.contracts.models import TaskContext, TaskEvent
from app.errors import AppError
from app.logging_setup import task_id as log_task_id

from .events import EventBus
from .repo import Repository
from .workspace import create_workspace, safe_join

LOGGER = logging.getLogger(__name__)
TERMINAL = {"completed", "failed"}


class TaskCapacityError(AppError):
    def __init__(self) -> None:
        super().__init__("TASK_CAPACITY", 429, "Maximum active task capacity reached")


class TaskRunner:
    def __init__(
        self,
        repo: Repository,
        bus: EventBus,
        services: Services,
        orchestrator: Orchestrator,
        settings: Settings,
    ) -> None:
        self.repo, self.bus, self.services = repo, bus, services
        self.orchestrator, self.settings = orchestrator, settings
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._slot_lock = asyncio.Lock()
        self._approved_tasks: set[str] = set()

    async def start(self, user_request: str, file_ids: list[str]) -> str:
        async with self._slot_lock:
            if len(self._tasks) >= self.settings.max_active_tasks:
                raise TaskCapacityError()
            task_id = str(uuid.uuid4())
            workspace = create_workspace(self.services.workspace_root, task_id)
            for file_id in file_ids:
                record = await self.repo.get_file(file_id)
                if record is not None:
                    source = Path(record["stored_path"])
                    if source.is_file():
                        # Preserve the trusted server-side extension (not raw filename)
                        # to keep workspace confinement and allow retriever to identify type.
                        extension = source.suffix.lower()
                        shutil.copy2(source, safe_join(workspace / "inputs", f"{file_id}{extension}"))
            await self.repo.create_task(task_id, user_request, self.settings.inference_mode)
            await self.bus.publish(
                task_id,
                "task_created",
                {"task_id": task_id, "inference_mode": self.settings.inference_mode},
            )
            await self.services.audit.emit("TASK_CREATED", "runner", "task_created", "ok", task_id)
            task = asyncio.create_task(
                self._run(task_id, user_request, file_ids, workspace), name=f"task-{task_id}"
            )
            self._tasks[task_id] = task
        return task_id

    async def _run(self, task_id: str, request: str, file_ids: list[str], workspace: Path) -> None:
        log_token = log_task_id.set(task_id)
        ctx = TaskContext(
            task_id=task_id,
            task_type=None,
            workspace=workspace,
            inference_mode=self.settings.inference_mode,
        )
        gen = self.orchestrator.run(ctx, request, file_ids, self.services)
        active_elapsed = 0.0
        terminal = False
        try:
            while True:
                task = await self.repo.get_task(task_id)
                approval = task is not None and task["current_state"] == "APPROVAL"
                limit = (
                    self.settings.approval_timeout_s
                    if approval
                    else self.settings.hard_task_timeout_s - active_elapsed
                )
                if limit <= 0:
                    raise TimeoutError
                started = time.monotonic()
                try:
                    event = await asyncio.wait_for(anext(gen), timeout=limit)
                except StopAsyncIteration:
                    break
                finally:
                    if not approval:
                        active_elapsed += time.monotonic() - started
                await self._apply(task_id, event)
                if event.type in TERMINAL:
                    terminal = True
                    break
            if not terminal:
                await self._fail(
                    task_id, "NO_TERMINAL_EVENT", "Task ended without a terminal event"
                )
        except (TimeoutError, asyncio.TimeoutError):
            await gen.aclose()
            await self._fail(task_id, "TASK_TIMEOUT", "Task exceeded its allowed execution time")
        except Exception:
            LOGGER.exception("task runner failed task_id=%s", task_id)
            await self._fail(task_id, "INTERNAL", "Task execution failed")
        finally:
            # Release any idle models held by this task to free memory for subsequent tasks.
            router = getattr(self.orchestrator, "router", None)
            if router is not None and getattr(router, "resources", None) is not None:
                await router.resources.unload_idle()
            self._tasks.pop(task_id, None)
            self._approved_tasks.discard(task_id)
            log_task_id.reset(log_token)

    async def shutdown(self) -> None:
        """Stop detached runners and persist an explicit shutdown failure."""
        active = list(self._tasks.items())
        for _, task in active:
            task.cancel()
        if active:
            await asyncio.gather(*(task for _, task in active), return_exceptions=True)
        for task_id, _ in active:
            task = await self.repo.get_task(task_id)
            if task is not None and task["current_state"] not in {"COMPLETE", "FAILED"}:
                await self._fail(task_id, "INTERRUPTED", "Backend shut down")

    async def _fail(self, task_id: str, code: str, message: str) -> None:
        await self._apply(
            task_id, TaskEvent(type="failed", data={"error": {"code": code, "message": message}})
        )

    async def _apply(self, task_id: str, event: TaskEvent) -> None:
        data = event.data
        fields: dict[str, Any] = {}
        if event.type == "state_changed":
            fields["current_state"] = data.get("state", "INTAKE")
            if data.get("task_type"):
                fields["task_type"] = data["task_type"]
        elif event.type == "plan":
            fields["plan"] = json.dumps(data.get("steps", []))
        elif event.type == "model_selected":
            fields["model_used"] = data.get("model_id")
        elif event.type == "tool_result":
            await self.repo.append_json_field(task_id, "tool_calls", data)
        elif event.type == "retrieval":
            for chunk in data.get("chunks", []):
                await self.repo.append_json_field(task_id, "retrieved_chunks", chunk)
        elif event.type == "verification":
            fields["verification_status"] = data.get("status", "pending")
        elif event.type == "pid_graph":
            fields["pid_graph"] = json.dumps(data.get("graph"))
        elif event.type == "approval_requested":
            fields["current_state"] = "APPROVAL"
        elif event.type == "completed":
            fields.update(
                current_state="COMPLETE", final_result=json.dumps(data.get("final_result"))
            )
        elif event.type == "failed":
            fields["current_state"] = "FAILED"
            await self.repo.append_json_field(task_id, "errors", data.get("error", {}))
        if fields:
            await self.repo.update_task_fields(task_id, **fields)
        await self._audit(task_id, event)
        await self.bus.publish(task_id, event.type, data)

    async def _audit(self, task_id: str, event: TaskEvent) -> None:
        category = {
            "task_created": "TASK_CREATED",
            "model_selected": "MODEL_SELECTED",
            "retrieval": "RETRIEVAL",
            "tool_proposed": "TOOL_PROPOSED",
            "repair": "REPAIR_STARTED",
            "approval_requested": "APPROVAL_REQUESTED",
            "completed": "TASK_COMPLETED",
            "failed": "TASK_FAILED",
        }.get(event.type)
        if event.type == "policy_decision":
            category = "POLICY_ALLOWED" if event.data.get("allowed") else "POLICY_DENIED"
        if event.type == "verification":
            category = {"pending": "VERIFICATION_STARTED", "failed": "VERIFICATION_FAILED"}.get(
                event.data.get("status")
            )
        if event.type == "artifact_validation":
            category = (
                "ARTIFACT_VALIDATED" if event.data.get("passed") else "ARTIFACT_VALIDATION_FAILED"
            )
        if category:
            await self.services.audit.emit(
                category,
                "runner",
                event.type,
                "error" if event.type == "failed" else "ok",
                task_id,
                event.data,
            )

    async def approve(
        self, task_id: str, approver: str, decision: str, note: str | None
    ) -> dict[str, Any]:
        task = await self.repo.get_task(task_id)
        if task is None:
            raise AppError("NOT_FOUND", 404, "Task not found")
        if task["current_state"] != "APPROVAL" or task_id in self._approved_tasks:
            raise AppError("CONFLICT", 409, "Task is not awaiting approval")
        self._approved_tasks.add(task_id)
        await self.repo.update_task_fields(task_id, approved_by=approver, approval_note=note)
        await self.bus.publish(
            task_id,
            "approved" if decision == "approve" else "rejected",
            {"approver": approver, "note": note},
        )
        await self.services.audit.emit(
            "APPROVED", "tasks", decision, "ok", task_id, {"approver": approver}
        )
        await self.orchestrator.approve(task_id, approver, decision, note)
        return await self.repo.get_task(task_id) or {}
