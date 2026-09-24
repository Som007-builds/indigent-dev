import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.config import Settings
from app.contracts.models import TaskContext
from app.core.audit import AuditLoggerImpl
from app.core.files import save_upload
from app.core.repo import Repository
from app.core.workspace import create_workspace, safe_join
from app.errors import AppError


def router(settings: Settings, repo: Repository, audit: AuditLoggerImpl, pid: object, artifacts: object) -> APIRouter:
    api = APIRouter(prefix="/api/pid")

    @api.post("/analyze")
    async def analyze(file: UploadFile = File(...)):  # noqa: B008
        record = await save_upload(file, kind="pid", settings=settings, repo=repo, audit=audit, size_limit_mb=settings.max_pid_image_mb)
        task_id = str(uuid.uuid4())
        workspace = create_workspace(settings.data_dir / "workspaces", task_id)
        await repo.create_task(task_id, "P&ID analysis", settings.inference_mode)
        ctx = TaskContext(task_id=task_id, task_type="pid_analysis", workspace=workspace, inference_mode=settings.inference_mode)
        await repo.update_task_fields(task_id, task_type="pid_analysis", current_state="TOOL")
        try:
            graph = await asyncio.wait_for(asyncio.to_thread(pid.extract_pid_graph, record.stored_path), settings.pid_timeout_s)  # type: ignore[attr-defined]
            graph_path = safe_join(workspace / "outputs", "pid-graph.json")
            graph_path.write_text(json.dumps(graph.model_dump(), sort_keys=True), encoding="utf-8")
            graph_artifact = await artifacts.register(ctx, "graph_json", str(graph_path))  # type: ignore[attr-defined]
            overlay_path = safe_join(workspace / "outputs", "pid-overlay" + Path(record.stored_path).suffix)
            source = Path(graph.overlay_image_path)
            if source.resolve() != overlay_path.resolve():
                shutil.copy2(source, overlay_path)
            overlay_artifact = await artifacts.register(ctx, "pid_overlay", str(overlay_path))  # type: ignore[attr-defined]
            payload = graph.model_dump()
            payload["overlay_artifact_id"] = overlay_artifact.artifact_id
            await repo.update_task_fields(task_id, pid_graph=json.dumps(payload), current_state="COMPLETE", final_result=json.dumps(payload))
            return {"task_id": task_id, "graph": payload, "artifact_ids": [graph_artifact.artifact_id, overlay_artifact.artifact_id]}
        except TimeoutError as exc:
            await repo.update_task_fields(task_id, current_state="FAILED", errors=json.dumps([{"code": "PID_TIMEOUT", "message": "P&ID analysis timed out"}]))
            raise AppError("PID_TIMEOUT", 500, "P&ID analysis timed out") from exc
        except Exception as exc:
            await repo.update_task_fields(task_id, current_state="FAILED", errors=json.dumps([{"code": "PID_FAILED", "message": "P&ID analysis failed"}]))
            raise AppError("PID_FAILED", 500, "P&ID analysis failed") from exc

    return api
