CREATE TABLE IF NOT EXISTS schema_version(v INTEGER);
CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, user_request TEXT NOT NULL, task_type TEXT, plan TEXT DEFAULT '[]',
 current_state TEXT NOT NULL DEFAULT 'INTAKE', inference_mode TEXT NOT NULL, model_used TEXT, tool_calls TEXT DEFAULT '[]',
 retrieved_chunks TEXT DEFAULT '[]', pid_graph TEXT, errors TEXT DEFAULT '[]', verification_status TEXT DEFAULT 'pending',
 final_result TEXT, requires_human_approval INTEGER DEFAULT 1, approved_by TEXT, approval_note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_task ON task_events(task_id, seq);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, ts TEXT NOT NULL, inference_mode TEXT NOT NULL,
 category TEXT NOT NULL, component TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, details TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_audit_task ON audit_log(task_id, id);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TABLE IF NOT EXISTS files(file_id TEXT PRIMARY KEY, task_id TEXT, kind TEXT NOT NULL, original_name TEXT NOT NULL, stored_path TEXT NOT NULL,
 size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, mime TEXT, ingest_status TEXT, ingest_error TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, artifact_type TEXT NOT NULL, path TEXT NOT NULL,
 artifact_hash TEXT NOT NULL, source_evidence_ids TEXT DEFAULT '[]', verification_status TEXT DEFAULT 'pending', metadata TEXT DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sovereignty_counters(id INTEGER PRIMARY KEY CHECK(id=1), external_api_calls INTEGER DEFAULT 0, external_connections INTEGER DEFAULT 0,
 external_bytes_out INTEGER DEFAULT 0, external_bytes_in INTEGER DEFAULT 0, denied_connections INTEGER DEFAULT 0, since TEXT);
