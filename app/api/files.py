import hashlib
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.files import CHUNK_SIZE, save_upload
from app.core.repo import Repository
from app.errors import AppError, PathRejectedError


def _resolve_stored_file(data_dir: Path, stored_path: str) -> Path:
    """Resolve a recorded ``stored_path`` and prove it lives inside ``data_dir``.

    ``save_upload`` records ``str(destination)``, which is absolute — it is built as
    ``data_dir / "uploads" / file_id / "<file_id><ext>"`` and returned already
    resolved. ``safe_join`` deliberately rejects absolute paths (it is built for
    untrusted *relative* input), so it cannot be used directly here. The same
    invariant is enforced instead: resolve, then require containment, and refuse any
    path that traverses outside ``DATA_DIR`` or reaches through a symlink.
    """
    candidate = Path(stored_path)
    root = data_dir.resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PathRejectedError("Stored path resolves outside DATA_DIR") from exc
    if not relative.parts or ".." in relative.parts:
        raise PathRejectedError("Stored path is not a file inside DATA_DIR")
    return resolved


def router(settings: Settings, repo: Repository, audit: AuditLoggerImpl) -> APIRouter:
    api = APIRouter(prefix="/api/files")

    @api.get("")
    async def list_files():
        records = await repo.list_files()
        return {"files": [{"file_id": item["file_id"], "name": item["original_name"], "size": item["size_bytes"], "sha256": item["sha256"], "mime": item["mime"], "kind": item["kind"], "created_at": item.get("created_at"), "download_url": f"/api/files/{item['file_id']}?download=1"} for item in records]}

    @api.get("/{file_id}")
    async def get_file(file_id: str, download: bool = False):
        """Fetch one stored file's metadata, or stream its bytes.

        Additive and non-breaking. The frontend previously fell back to
        ``/api/files/{name}``, which had no matching route, so every document
        download 404'd (Frontend-fix.md item 2.2).
        """
        record = await repo.get_file(file_id)
        if record is None:
            raise AppError("NOT_FOUND", 404, "File not found")

        resolved = _resolve_stored_file(settings.data_dir, record["stored_path"])

        if not resolved.is_file():
            raise AppError("NOT_FOUND", 404, "File is recorded but missing from storage")

        if not download:
            return {
                "file_id": record["file_id"],
                "name": record["original_name"],
                "size": record["size_bytes"],
                "sha256": record["sha256"],
                "mime": record["mime"],
                "kind": record["kind"],
                "created_at": record.get("created_at"),
                "download_url": f"/api/files/{record['file_id']}?download=1",
            }

        # Re-verify the digest recorded at upload time, so a file replaced or
        # truncated on disk is reported rather than silently served.
        digest = hashlib.sha256()
        with resolved.open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        if digest.hexdigest() != record["sha256"]:
            raise AppError(
                "FILE_CORRUPT",
                500,
                "Stored file no longer matches the sha256 recorded at upload",
            )

        await audit.emit(
            "FILE_DOWNLOADED",
            "files",
            "download",
            "ok",
            record.get("task_id"),
            {"file_id": record["file_id"], "size_bytes": record["size_bytes"]},
        )
        return FileResponse(resolved, filename=record["original_name"], media_type=record["mime"])

    @api.post("/upload")
    async def upload(file: list[UploadFile] = File(...), task_id: str | None = Form(None)):  # noqa: B008
        records = [await save_upload(item, kind="upload", settings=settings, repo=repo, audit=audit, task_id=task_id) for item in file]
        return {"files": [{"file_id": item.file_id, "name": item.original_name, "size": item.size_bytes, "sha256": item.sha256, "mime": item.mime, "kind": item.kind, "download_url": f"/api/files/{item.file_id}?download=1"} for item in records]}

    return api
