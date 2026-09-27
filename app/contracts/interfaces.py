from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Literal, Protocol

from .models import (
    ArtifactManifest,
    FileRecord,
    IngestResult,
    PIDGraph,
    PolicyDecision,
    TaskContext,
    TaskEvent,
    ToolRequest,
    ToolResult,
    ValidationReport,
)


class Orchestrator(Protocol):
    def run(
        self, ctx: TaskContext, user_request: str, file_ids: list[str], services: "Services"
    ) -> AsyncIterator[TaskEvent]: ...
    async def approve(
        self, task_id: str, approver: str, decision: Literal["approve", "reject"], note: str | None
    ) -> None: ...


class PolicyValidator(Protocol):
    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision: ...


class RagIngestor(Protocol):
    async def ingest(self, file: FileRecord) -> IngestResult: ...


class PidPipeline(Protocol):
    async def extract_pid_graph(self, image_path: str) -> PIDGraph: ...


class MlTools(Protocol):
    async def call(self, tool: str, ctx: TaskContext, args: dict) -> dict: ...


class ArtifactValidator(Protocol):
    async def validate(self, m: ArtifactManifest) -> ValidationReport: ...


class ModelsStatus(Protocol):
    def status(self) -> dict: ...


class ToolRuntime(Protocol):
    async def execute(self, ctx: TaskContext, decision: PolicyDecision) -> ToolResult: ...


class ArtifactStore(Protocol):
    async def register(
        self,
        ctx: TaskContext,
        artifact_type: str,
        path: str,
        source_evidence_ids: list[str] = [],
        metadata: dict = {},
    ) -> ArtifactManifest: ...
    async def set_verification_status(self, artifact_id: str, status: str) -> None: ...
    async def get(self, artifact_id: str) -> ArtifactManifest: ...
    async def verify_integrity(self, artifact_id: str) -> bool: ...
    async def package_code(self, ctx: TaskContext) -> ArtifactManifest: ...
    async def create_stub_docx(self, ctx: TaskContext) -> ArtifactManifest: ...


class AuditLogger(Protocol):
    async def emit(
        self,
        category: str,
        component: str,
        action: str,
        status: str = "info",
        task_id: str | None = None,
        details: dict = {},
    ) -> None: ...


class Sovereignty(Protocol):
    async def record_external_call(self, provider: str, bytes_out: int, bytes_in: int) -> None: ...
    async def snapshot(self) -> dict: ...


@dataclass
class Services:
    runtime: ToolRuntime
    artifacts: ArtifactStore
    audit: AuditLogger
    sovereignty: Sovereignty
    policy: PolicyValidator
    ml_tools: MlTools
    artifact_validator: ArtifactValidator
    workspace_root: Path
