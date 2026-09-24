import hashlib
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.contracts.models import FileRecord
from app.core.audit import AuditLoggerImpl
from app.core.repo import Repository
from app.core.workspace import safe_join
from app.errors import AppError

CHUNK_SIZE = 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".json"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}


def _validate_magic(path: Path, extension: str) -> str:
    with path.open("rb") as source:
        head = source.read(16)
    if extension == ".pdf":
        if not head.startswith(b"%PDF-"):
            raise AppError("UNSUPPORTED_MEDIA", 415, "File does not have valid PDF content")
        return "application/pdf"
    if extension in OFFICE_EXTENSIONS:
        if not head.startswith(b"PK\x03\x04"):
            raise AppError("UNSUPPORTED_MEDIA", 415, "File does not have valid Office content")
        return "application/vnd.openxmlformats-officedocument"
    if extension in IMAGE_EXTENSIONS:
        try:
            with Image.open(path) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise AppError("UNSUPPORTED_MEDIA", 415, "File does not have valid image content") from exc
        return f"image/{'jpeg' if extension in {'.jpg', '.jpeg'} else extension[1:]}"
    return "text/plain"


async def save_upload(
    upload: UploadFile, *, kind: str, settings: Settings, repo: Repository, audit: AuditLoggerImpl,
    task_id: str | None = None, size_limit_mb: int | None = None,
) -> FileRecord:
    name = upload.filename or ""
    extension = Path(name).suffix.lower()
    allowed = IMAGE_EXTENSIONS if kind == "pid" else ALLOWED_EXTENSIONS
    if extension not in allowed:
        raise AppError("UNSUPPORTED_MEDIA", 415, "Unsupported file type")
    file_id = uuid.uuid4().hex
    directory = settings.data_dir / ("pid" if kind == "pid" else "uploads") / file_id
    destination = safe_join(directory, f"{file_id}{extension}")
    directory.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    limit = (size_limit_mb or settings.max_upload_mb) * 1024 * 1024
    try:
        with destination.open("xb") as target:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise AppError("PAYLOAD_TOO_LARGE", 413, "Upload exceeds size limit")
                digest.update(chunk)
                target.write(chunk)
        mime = _validate_magic(destination, extension)
    except Exception:
        if directory.exists():
            shutil.rmtree(directory)
        raise
    finally:
        await upload.close()
    record = FileRecord(file_id=file_id, task_id=task_id, kind=kind, original_name=name,
                        stored_path=str(destination), size_bytes=size, sha256=digest.hexdigest(), mime=mime)
    await repo.insert_file(record, "pending" if kind == "knowledge" else None)
    await audit.emit("FILE_UPLOADED", "files", "upload saved", "ok", task_id, {"name": name, "size": size})
    return record
