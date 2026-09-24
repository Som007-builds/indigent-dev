from fastapi import APIRouter, File, Form, UploadFile

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.files import save_upload
from app.core.repo import Repository


def router(settings: Settings, repo: Repository, audit: AuditLoggerImpl) -> APIRouter:
    api = APIRouter(prefix="/api/files")

    @api.post("/upload")
    async def upload(file: list[UploadFile] = File(...), task_id: str | None = Form(None)):  # noqa: B008
        records = [await save_upload(item, kind="upload", settings=settings, repo=repo, audit=audit, task_id=task_id) for item in file]
        return {"files": [{"file_id": item.file_id, "name": item.original_name, "size": item.size_bytes, "sha256": item.sha256, "mime": item.mime, "kind": item.kind} for item in records]}

    return api
