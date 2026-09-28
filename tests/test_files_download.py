"""`GET /api/files/{file_id}` must serve the bytes that were actually uploaded.

The route did not exist. The frontend fell back to `/api/files/{name}`, which matched
nothing, so every document download 404'd — the Documents tab looked functional and
could not retrieve anything. The route is additive (`Frontend-fix.md` item 2.2).

Three things are asserted beyond the happy path, because all three are ways a file
route can become a hole rather than a feature:

* containment — a `stored_path` that resolves outside `DATA_DIR` is refused, so a
  corrupted or tampered database row cannot be turned into an arbitrary file read;
* integrity — a file whose bytes changed on disk after upload is reported, not
  silently served under the digest it was registered with;
* error shape — an unknown id returns the standard error envelope, not a 500.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def data_dir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def client(data_dir):
    """Entered as a context manager so the lifespan applies the schema.

    ``create_app`` initializes SQLite and the services in its lifespan handler, so a
    bare, un-entered ``TestClient`` has no tables.
    """
    with TestClient(create_app(Settings(data_dir=data_dir, inference_mode="local"))) as c:
        yield c


def _upload(client: TestClient, name: str = "scan.png", data: bytes = PNG_BYTES) -> dict:
    res = client.post("/api/files/upload", files={"file": (name, data, "image/png")})
    assert res.status_code == 200, res.text
    return res.json()["files"][0]


def _rewrite_stored_path(data_dir: Path, file_id: str, new_path: Path) -> None:
    with sqlite3.connect(data_dir / "db.sqlite") as conn:
        conn.execute("UPDATE files SET stored_path=? WHERE file_id=?", (str(new_path), file_id))
        conn.commit()


def test_list_exposes_a_download_url_keyed_by_file_id(client: TestClient) -> None:
    """The frontend must be able to build a URL from the id alone, never the name."""
    uploaded = _upload(client)

    body = client.get("/api/files").json()
    listed = next(item for item in body["files"] if item["file_id"] == uploaded["file_id"])

    assert listed["download_url"] == f"/api/files/{uploaded['file_id']}?download=1"


def test_download_returns_the_exact_uploaded_bytes(client: TestClient) -> None:
    uploaded = _upload(client)

    res = client.get(f"/api/files/{uploaded['file_id']}", params={"download": 1})

    assert res.status_code == 200
    assert res.content == PNG_BYTES
    assert hashlib.sha256(res.content).hexdigest() == uploaded["sha256"]


def test_metadata_without_the_download_flag_returns_no_bytes(client: TestClient) -> None:
    uploaded = _upload(client)

    res = client.get(f"/api/files/{uploaded['file_id']}")

    assert res.status_code == 200
    body = res.json()
    assert body["file_id"] == uploaded["file_id"]
    assert body["name"] == "scan.png"
    assert body["sha256"] == uploaded["sha256"]
    assert body["download_url"] == f"/api/files/{uploaded['file_id']}?download=1"


def test_unknown_file_id_returns_the_standard_error_envelope(client: TestClient) -> None:
    res = client.get("/api/files/does-not-exist", params={"download": 1})

    assert res.status_code == 404
    error = res.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"]


def test_a_recorded_but_deleted_file_reports_not_found(client: TestClient, data_dir: Path) -> None:
    """A database row pointing at nothing must not become a 500."""
    uploaded = _upload(client)
    for path in (data_dir / "uploads").rglob("*"):
        if path.is_file():
            path.unlink()

    res = client.get(f"/api/files/{uploaded['file_id']}", params={"download": 1})

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_bytes_changed_on_disk_are_reported_not_served(client: TestClient, data_dir: Path) -> None:
    """A replaced file must not be returned under the digest it was registered with."""
    uploaded = _upload(client)
    stored = next(p for p in (data_dir / "uploads").rglob("*.png") if p.is_file())
    stored.write_bytes(PNG_BYTES + b"tampered")

    res = client.get(f"/api/files/{uploaded['file_id']}", params={"download": 1})

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "FILE_CORRUPT"


def test_a_stored_path_escaping_data_dir_is_refused(client: TestClient, data_dir: Path) -> None:
    """Containment is the point of the route: a row must not read outside DATA_DIR."""
    uploaded = _upload(client)
    secret = data_dir.parent / "outside-the-workspace.txt"
    secret.write_text("must never be served", encoding="utf-8")
    _rewrite_stored_path(data_dir, uploaded["file_id"], secret)

    res = client.get(f"/api/files/{uploaded['file_id']}", params={"download": 1})

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PATH_REJECTED"


def test_download_is_audited(client: TestClient, data_dir: Path) -> None:
    """A read of a stored file is an access event and belongs in the ledger."""
    uploaded = _upload(client)

    assert client.get(f"/api/files/{uploaded['file_id']}", params={"download": 1}).status_code == 200

    with sqlite3.connect(data_dir / "db.sqlite") as conn:
        rows = conn.execute(
            "SELECT category, component, action FROM audit_log WHERE category = ?",
            ("FILE_DOWNLOADED",),
        ).fetchall()

    assert rows == [("FILE_DOWNLOADED", "files", "download")]
