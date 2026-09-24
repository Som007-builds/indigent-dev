import io

import pytest
from fastapi import UploadFile

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.files import save_upload
from app.core.repo import Repository
from app.core.workspace import safe_join
from app.errors import AppError, PathRejectedError


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "a/../../b", r"C:\\x", "bad\x00path"])
def test_safe_join_rejects_escapes(tmp_path, path):
    with pytest.raises(PathRejectedError):
        safe_join(tmp_path, path)


def test_safe_join_allows_nested_path(tmp_path):
    assert safe_join(tmp_path, "nested/file.txt") == (tmp_path / "nested" / "file.txt").resolve()


def test_safe_join_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(PathRejectedError):
        safe_join(tmp_path, "link/file.txt")


async def _services(tmp_path):
    settings = Settings(data_dir=tmp_path, max_upload_mb=1)
    repo = Repository(Database(tmp_path / "db.sqlite"))
    await repo.db.initialize()
    return settings, repo, AuditLoggerImpl(repo, settings)


@pytest.mark.asyncio
async def test_oversize_upload_removes_partial_file(tmp_path):
    settings, repo, audit = await _services(tmp_path)
    upload = UploadFile(io.BytesIO(b"x" * (1024 * 1024 + 1)), filename="large.txt")
    with pytest.raises(AppError) as error:
        await save_upload(upload, kind="upload", settings=settings, repo=repo, audit=audit)
    assert error.value.http_status == 413
    assert not list((tmp_path / "uploads").glob("**/*"))


@pytest.mark.asyncio
async def test_renamed_executable_is_rejected(tmp_path):
    settings, repo, audit = await _services(tmp_path)
    upload = UploadFile(io.BytesIO(b"MZ executable"), filename="not-a-pdf.pdf")
    with pytest.raises(AppError) as error:
        await save_upload(upload, kind="upload", settings=settings, repo=repo, audit=audit)
    assert error.value.http_status == 415
