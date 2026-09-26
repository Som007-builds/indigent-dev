import json
from datetime import UTC, datetime
from typing import Any

from app.contracts.models import ArtifactManifest, FileRecord

from .db import Database


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create_task(self, task_id: str, user_request: str, inference_mode: str) -> None:
        now = _now()
        async with self.db.connection() as conn:
            await conn.execute(
                "INSERT INTO tasks(task_id,user_request,inference_mode,created_at,updated_at) VALUES(?,?,?,?,?)",
                (task_id, user_request, inference_mode, now, now),
            )
            await conn.commit()

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            row = await (
                await conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
            ).fetchone()
        return dict(row) if row else None

    async def update_task_fields(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        columns = ", ".join(f"{name}=?" for name in fields)
        async with self.db.connection() as conn:
            await conn.execute(
                f"UPDATE tasks SET {columns} WHERE task_id=?", (*fields.values(), task_id)
            )
            await conn.commit()

    async def append_json_field(self, task_id: str, field: str, value: Any) -> None:
        if field not in {"plan", "tool_calls", "retrieved_chunks", "errors"}:
            raise ValueError("invalid JSON field")
        task = await self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        values = json.loads(task[field] or "[]")
        values.append(value)
        await self.update_task_fields(task_id, **{field: json.dumps(values)})

    async def insert_event(self, task_id: str, event_type: str, data: dict[str, Any]) -> int:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO task_events(task_id,ts,type,data) VALUES(?,?,?,?)",
                (task_id, _now(), event_type, json.dumps(data)),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def list_events(self, task_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT * FROM task_events WHERE task_id=? AND seq>? ORDER BY seq",
                    (task_id, after_seq),
                )
            ).fetchall()
        return [dict(row) for row in rows]

    async def insert_file(self, file: FileRecord, ingest_status: str | None = None) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                "INSERT INTO files(file_id,task_id,kind,original_name,stored_path,size_bytes,sha256,mime,ingest_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    file.file_id,
                    file.task_id,
                    file.kind,
                    file.original_name,
                    file.stored_path,
                    file.size_bytes,
                    file.sha256,
                    file.mime,
                    ingest_status,
                    _now(),
                ),
            )
            await conn.commit()

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        return await self._one("files", "file_id", file_id)

    async def update_ingest(self, file_id: str, status: str, error: str | None = None) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                "UPDATE files SET ingest_status=?, ingest_error=? WHERE file_id=?",
                (status, error, file_id),
            )
            await conn.commit()

    async def insert_artifact(self, artifact: ArtifactManifest) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    artifact.artifact_id,
                    artifact.task_id,
                    artifact.artifact_type,
                    artifact.path,
                    artifact.artifact_hash,
                    json.dumps(artifact.source_evidence_ids),
                    artifact.verification_status,
                    json.dumps(artifact.metadata),
                    artifact.created_at,
                ),
            )
            await conn.commit()

    async def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return await self._one("artifacts", "artifact_id", artifact_id)

    async def list_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            rows = await (
                await conn.execute("SELECT * FROM artifacts WHERE task_id=?", (task_id,))
            ).fetchall()
        return [dict(row) for row in rows]

    async def insert_audit(self, **record: Any) -> int:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO audit_log(task_id,ts,inference_mode,category,component,action,status,details) VALUES(?,?,?,?,?,?,?,?)",
                (
                    record.get("task_id"),
                    _now(),
                    record["inference_mode"],
                    record["category"],
                    record["component"],
                    record["action"],
                    record["status"],
                    json.dumps(record.get("details", {})),
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def list_audit(self, task_id: str | None = None) -> list[dict[str, Any]]:
        query, args = (
            ("SELECT * FROM audit_log ORDER BY id", ())
            if task_id is None
            else ("SELECT * FROM audit_log WHERE task_id=? ORDER BY id", (task_id,))
        )
        async with self.db.connection() as conn:
            rows = await (await conn.execute(query, args)).fetchall()
        return [dict(row) for row in rows]

    async def get_counters(self) -> dict[str, Any]:
        async with self.db.connection() as conn:
            row = await (
                await conn.execute("SELECT * FROM sovereignty_counters WHERE id=1")
            ).fetchone()
            if row is None:
                # OR IGNORE: a denied-egress counter may have created this row
                # concurrently between the SELECT and the INSERT.
                await conn.execute(
                    "INSERT OR IGNORE INTO sovereignty_counters(id,since) VALUES(1,?)", (_now(),)
                )
                await conn.commit()
                row = await (
                    await conn.execute("SELECT * FROM sovereignty_counters WHERE id=1")
                ).fetchone()
        return dict(row)

    async def increment_counter(self, field: str, amount: int = 1) -> None:
        if field not in {
            "external_api_calls",
            "external_connections",
            "external_bytes_out",
            "external_bytes_in",
            "denied_connections",
        }:
            raise ValueError("invalid counter")
        async with self.db.connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO sovereignty_counters(id,since) VALUES(1,?)", (_now(),)
            )
            await conn.execute(
                f"UPDATE sovereignty_counters SET {field}={field}+? WHERE id=1", (amount,)
            )
            await conn.commit()

    async def recover_interrupted_tasks(self) -> list[str]:
        async with self.db.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT task_id, errors FROM tasks WHERE current_state NOT IN ('COMPLETE','FAILED')"
                )
            ).fetchall()
            now = _now()
            task_ids: list[str] = []
            for row in rows:
                errors = json.loads(row["errors"] or "[]")
                errors.append({"code": "INTERRUPTED", "message": "backend restarted"})
                await conn.execute(
                    "UPDATE tasks SET current_state='FAILED', errors=?, updated_at=? WHERE task_id=?",
                    (json.dumps(errors), now, row["task_id"]),
                )
                task_ids.append(str(row["task_id"]))
            await conn.commit()
        return task_ids

    async def _one(self, table: str, key: str, value: str) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            row = await (
                await conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,))
            ).fetchone()
        return dict(row) if row else None
