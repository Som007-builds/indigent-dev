from fastapi import APIRouter, BackgroundTasks, File, UploadFile

from app.config import Settings
from app.contracts.models import FileRecord
from app.core.audit import AuditLoggerImpl
from app.core.files import save_upload
from app.core.repo import Repository


def router(settings: Settings, repo: Repository, audit: AuditLoggerImpl, rag: object) -> APIRouter:
    api = APIRouter(prefix="/api/knowledge")

    async def ingest(record: FileRecord) -> None:
        await repo.update_ingest(record.file_id, "ingesting")
        await audit.emit("INGEST_STARTED", "knowledge", "ingest", "info", details={"file_id": record.file_id})
        try:
            result = await rag.ingest(record)  # type: ignore[attr-defined]
            if result.status != "ok":
                raise ValueError(result.error or "ingestion failed")
            await repo.update_ingest(record.file_id, "ready")
        except Exception as exc:
            await repo.update_ingest(record.file_id, "failed", str(exc))
            await audit.emit("INGEST_FAILED", "knowledge", "ingest", "error", details={"file_id": record.file_id})

    @api.get("")
    async def list_knowledge():
        records = await repo.list_files(kind="knowledge")
        return {"files": [{"file_id": item["file_id"], "name": item["original_name"], "size": item["size_bytes"], "sha256": item["sha256"], "mime": item["mime"], "ingest_status": item.get("ingest_status", "ready"), "ingest_error": item.get("ingest_error"), "created_at": item.get("created_at")} for item in records]}

    @api.post("/upload")
    async def upload(background: BackgroundTasks, file: list[UploadFile] = File(...)):  # noqa: B008
        records = [await save_upload(item, kind="knowledge", settings=settings, repo=repo, audit=audit) for item in file]
        for record in records:
            background.add_task(ingest, record)
        return {"files": [{"file_id": item.file_id, "name": item.original_name, "size": item.size_bytes, "sha256": item.sha256, "mime": item.mime, "ingest_status": "pending"} for item in records]}

    @api.get("/{file_id}")
    async def get(file_id: str):
        record = await repo.get_file(file_id)
        if record is None or record["kind"] != "knowledge":
            from app.errors import AppError
            raise AppError("NOT_FOUND", 404, "Knowledge file not found")
        return {"file_id": file_id, "name": record["original_name"], "ingest_status": record["ingest_status"], "ingest_error": record["ingest_error"]}

    return api
