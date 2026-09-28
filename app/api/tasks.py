import json

from fastapi import APIRouter, Header
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.artifacts import annotate_size
from app.core.events import EventBus
from app.core.repo import Repository
from app.core.taskrunner import TaskRunner
from app.errors import AppError


class ApprovalRequest(BaseModel):
    approver: str
    decision: str
    note: str | None = None


def router(runner: TaskRunner, bus: EventBus, repo: Repository) -> APIRouter:
    api = APIRouter(prefix="/api/tasks")

    @api.get("")
    async def list_tasks(limit: int = 50):
        tasks = await repo.list_tasks(limit)
        return {"tasks": tasks}

    @api.get("/timeline/all")
    async def global_timeline():
        return {"entries": await repo.list_audit()}

    @api.get("/{task_id}/stream")
    async def stream(task_id: str, last_event_id: str | None = Header(None)):
        if await repo.get_task(task_id) is None:
            raise AppError("NOT_FOUND", 404, "Task not found")
        try:
            after = int(last_event_id or 0)
        except ValueError:
            after = 0

        async def events():
            async for event in bus.subscribe(task_id, after):
                yield {"id": str(event["id"]), "event": event["type"], "data": json.dumps(event)}
                if event["type"] in {"completed", "failed"}:
                    break

        return EventSourceResponse(events(), ping=15)

    @api.get("/{task_id}")
    async def get_task(task_id: str):
        task = await repo.get_task(task_id)
        if task is None:
            raise AppError("NOT_FOUND", 404, "Task not found")
        for field in (
            "plan",
            "tool_calls",
            "retrieved_chunks",
            "errors",
            "pid_graph",
            "final_result",
        ):
            if task.get(field) is not None:
                task[field] = json.loads(task[field])
        artifacts = [annotate_size(row) for row in await repo.list_artifacts(task_id)]
        for artifact in artifacts:
            for field in ("source_evidence_ids", "metadata"):
                artifact[field] = json.loads(artifact[field])
        task["artifacts"] = artifacts
        return task

    @api.get("/{task_id}/timeline")
    async def timeline(task_id: str):
        if await repo.get_task(task_id) is None:
            raise AppError("NOT_FOUND", 404, "Task not found")
        return {"task_id": task_id, "entries": await repo.list_audit(task_id)}

    @api.post("/{task_id}/approve")
    async def approve(task_id: str, payload: ApprovalRequest):
        if payload.decision not in {"approve", "reject"}:
            raise AppError("VALIDATION_ERROR", 422, "Invalid decision")
        task = await runner.approve(task_id, payload.approver, payload.decision, payload.note)
        return {
            "task_id": task_id,
            "current_state": task["current_state"],
            "approved_by": payload.approver,
        }

    return api
