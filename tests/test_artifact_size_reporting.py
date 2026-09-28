"""Artifact sizes must be real bytes, reported additively.

No artifact size is ever persisted: the `artifacts` table (G10) has no size column and
`ArtifactManifest` (G8) has no size field. Because the frontend therefore had nothing
real to display, it rendered the literal string "Validated deliverable" in a field the
UI shows as an artifact's size (`Frontend-fix.md` item 3.2). `annotate_size` closes the
gap by stat-ing the artifact at read time.

Covered here, because each of these is a way the fix could turn a lie into a different
lie:

* a real file reports its real byte count, not a rounded or invented figure;
* a missing file reports ``None`` -- "not reported" -- and *not* ``0``, because zero
  bytes is a fact about a real (empty) file and would read as a successful download of
  an empty document;
* a directory on the ``path`` reports ``None`` rather than the inode size;
* the field is additive: everything the manifest already carried is still present, and
  the routes that never had a size are untouched;
* the default ``CORS_ORIGINS`` names the origins this app is actually served from,
  since the old default (Vite's 5173) never included the Next.js port and was masked
  only by the same-origin proxy (`Frontend-fix.md` item 3.3).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.artifacts import annotate_size
from app.main import create_app

PAYLOAD = b"local inference only, never leaving this machine\n"


@pytest.fixture
def data_dir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(Settings(data_dir=data_dir, inference_mode="local"))) as c:
        yield c


def _seed_artifact(data_dir: Path, artifact_id: str, task_id: str, name: str, body: bytes) -> str:
    """Write a file into a workspace and register it in the DB the way the store does.

    The digest is the real one, because the download route re-hashes and refuses to
    serve a file that no longer matches its registered ``artifact_hash``.
    """
    outputs = data_dir / "workspaces" / task_id / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / name
    path.write_bytes(body)
    db = data_dir / "db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)",
            (
                artifact_id,
                task_id,
                "docx",
                str(path),
                hashlib.sha256(body).hexdigest(),
                json.dumps([]),
                "pending",
                json.dumps({}),
                "2026-09-28T10:00:00Z",
            ),
        )
    return str(path)


def _seed_task(data_dir: Path, task_id: str) -> None:
    """Insert a task row, naming columns so the test survives a schema addition."""
    with sqlite3.connect(data_dir / "db.sqlite") as conn:
        conn.execute(
            """INSERT INTO tasks (
                task_id, user_request, task_type, current_state, inference_mode,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                task_id,
                "make me a note",
                "inspection",
                "COMPLETE",
                "local",
                "2026-09-28T10:00:00Z",
                "2026-09-28T10:00:00Z",
            ),
        )


# --------------------------------------------------------------------------- unit


def test_annotate_size_reports_real_bytes(tmp_path: Path) -> None:
    path = tmp_path / "note.docx"
    path.write_bytes(PAYLOAD)
    assert annotate_size({"path": str(path)})["size_bytes"] == len(PAYLOAD)


def test_annotate_size_is_none_when_the_file_is_gone(tmp_path: Path) -> None:
    """Absent is not zero. An empty file is a fact; a deleted one is an absence."""
    missing = tmp_path / "deleted.docx"
    assert annotate_size({"path": str(missing)})["size_bytes"] is None


def test_annotate_size_is_none_for_a_directory(tmp_path: Path) -> None:
    """`stat` on a directory returns an inode size, which is not an artifact size."""
    assert annotate_size({"path": str(tmp_path)})["size_bytes"] is None


def test_annotate_size_does_not_mutate_its_input() -> None:
    record = {"path": str(Path(__file__))}
    annotate_size(record)
    assert "size_bytes" not in record


def test_annotate_size_preserves_every_existing_field() -> None:
    path = Path(__file__)
    enriched = annotate_size(
        {"artifact_id": "a1", "task_id": "t1", "artifact_type": "docx", "path": str(path)}
    )
    assert enriched["artifact_id"] == "a1"
    assert enriched["artifact_type"] == "docx"


# --------------------------------------------------------------------------- routes


def test_artifact_manifest_route_reports_real_size(client: TestClient, data_dir: Path) -> None:
    _seed_artifact(data_dir, "art-size-1", "task-size-1", "report.docx", PAYLOAD)
    res = client.get("/api/artifacts/art-size-1")
    assert res.status_code == 200, res.text
    assert res.json()["size_bytes"] == len(PAYLOAD)


def test_task_route_reports_real_size(client: TestClient, data_dir: Path) -> None:
    _seed_task(data_dir, "task-size-2")
    _seed_artifact(data_dir, "art-size-2", "task-size-2", "report.docx", PAYLOAD)
    res = client.get("/api/tasks/task-size-2")
    assert res.status_code == 200, res.text
    artifacts = res.json()["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["size_bytes"] == len(PAYLOAD)
    # Still JSON-decoded, not left as text: the enrichment must not disturb the columns
    # the route has always decoded.
    assert artifacts[0]["source_evidence_ids"] == []
    assert artifacts[0]["metadata"] == {}


def test_missing_artifact_file_reports_none_not_zero(client: TestClient, data_dir: Path) -> None:
    _seed_artifact(data_dir, "art-size-3", "task-size-3", "report.docx", PAYLOAD)
    Path(data_dir / "workspaces" / "task-size-3" / "outputs" / "report.docx").unlink()
    res = client.get("/api/artifacts/art-size-3")
    # The route 404s before reaching the annotation when the file is absent, which is
    # the stronger guarantee: a deleted artifact is not downloadable at all.
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_download_still_streams_exact_bytes(client: TestClient, data_dir: Path) -> None:
    """The size must describe the same bytes `?download=1` serves."""
    _seed_artifact(data_dir, "art-size-4", "task-size-4", "report.docx", PAYLOAD)
    res = client.get("/api/artifacts/art-size-4?download=1")
    assert res.status_code == 200, res.text
    assert res.content == PAYLOAD
    assert len(res.content) == client.get("/api/artifacts/art-size-4").json()["size_bytes"]


# ---------------------------------------------------------------------------- CORS


def test_cors_default_includes_the_nextjs_port() -> None:
    """Item 3.3: 5173 is Vite's port; this app serves on 3000."""
    origins = Settings().cors_origin_list
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    # The old default is retained, so a Vite-based caller still works.
    assert "http://localhost:5173" in origins


def test_cors_middleware_admits_the_nextjs_origin(client: TestClient) -> None:
    res = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_middleware_refuses_an_unknown_origin(client: TestClient) -> None:
    res = client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert res.headers.get("access-control-allow-origin") is None
