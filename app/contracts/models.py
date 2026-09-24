from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

InferenceMode = Literal["local", "groq"]
TaskState = Literal[
    "INTAKE",
    "CLASSIFY",
    "PLAN",
    "RETRIEVE",
    "TOOL",
    "VERIFY",
    "REPAIR",
    "ARTIFACT",
    "ARTIFACT_VALIDATE",
    "APPROVAL",
    "COMPLETE",
    "FAILED",
]


class TaskEvent(BaseModel):
    type: str
    data: dict = Field(default_factory=dict)


class TaskContext(BaseModel):
    task_id: str
    task_type: str | None
    workspace: Path
    inference_mode: InferenceMode


class ToolRequest(BaseModel):
    tool: str
    args: dict


class PolicyDecision(BaseModel):
    allowed: bool
    tool: str
    validated_args: dict = Field(default_factory=dict)
    decision_id: str
    reason: str | None = None
    requires_approval: bool = False


class ToolResult(BaseModel):
    ok: bool
    tool: str
    data: dict = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    truncated: bool = False
    resource_events: list[str] = Field(default_factory=list)
    error: str | None = None


class FileRecord(BaseModel):
    file_id: str
    task_id: str | None
    kind: Literal["upload", "knowledge", "pid"]
    original_name: str
    stored_path: str
    size_bytes: int
    sha256: str
    mime: str


class IngestResult(BaseModel):
    file_id: str
    status: Literal["ok", "failed"]
    chunks: int = 0
    error: str | None = None


class ArtifactManifest(BaseModel):
    artifact_id: str
    task_id: str
    artifact_type: Literal["docx", "xlsx", "graph_json", "code_package", "pid_overlay"]
    path: str
    created_at: str
    artifact_hash: str
    source_evidence_ids: list[str] = Field(default_factory=list)
    verification_status: Literal["pending", "passed", "failed"] = "pending"
    metadata: dict = Field(default_factory=dict)


class ValidationReport(BaseModel):
    passed: bool
    checks: list[dict]


class PIDGraph(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    overlay_image_path: str
    narrative: str
    confidence_summary: dict
