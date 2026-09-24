import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from docx import Document

from app.config import Settings
from app.contracts.interfaces import Services
from app.contracts.models import ArtifactManifest, PolicyDecision, TaskContext, ToolResult
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.repo import Repository
from app.errors import ToolNotAllowedError
from app.runtime.executor import ToolRuntimeImpl
from app.stubs.artifact_validator import StubArtifactValidator
from app.stubs.ml_tools import StubMlTools
from app.stubs.orchestrator import StubOrchestrator
from app.stubs.pid import StubPid
from app.stubs.policy import StubPolicy
from app.stubs.rag import StubRag


class StubRuntime:
    async def execute(self, ctx: TaskContext, decision: PolicyDecision) -> ToolResult:
        if not decision.allowed:
            raise ToolNotAllowedError()
        return ToolResult(ok=True, tool=decision.tool)


class StubArtifacts:
    async def register(self, ctx: TaskContext, artifact_type: str, path: str, **kwargs: object) -> ArtifactManifest:
        file_path = Path(path)
        return ArtifactManifest(
            artifact_id=str(uuid.uuid4()), task_id=ctx.task_id, artifact_type=artifact_type,
            path=str(file_path), created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            artifact_hash=hashlib.sha256(file_path.read_bytes()).hexdigest(),
        )

    async def create_stub_docx(self, ctx: TaskContext) -> ArtifactManifest:
        output = ctx.workspace / "outputs"
        output.mkdir(parents=True, exist_ok=True)
        path = output / "stub-report.docx"
        document = Document()
        document.add_paragraph("Indigent stub report")
        document.save(path)
        return ArtifactManifest(
            artifact_id=str(uuid.uuid4()),
            task_id=ctx.task_id,
            artifact_type="docx",
            path=str(path),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            artifact_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )


class NullAudit:
    async def emit(self, **kwargs: object) -> None:
        return None


class NullSovereignty:
    async def record_external_call(self, provider: str, bytes_out: int, bytes_in: int) -> None:
        return None

    async def snapshot(self) -> dict:
        return {}


def build_services(settings: Settings) -> tuple[Services, object, object, object]:
    if settings.joy_modules == "real":
        raise RuntimeError("JOY_MODULES=real requires Joy's modules")
    workspace_root = Path(settings.data_dir) / "workspaces"
    repository = Repository(Database(Path(settings.data_dir) / "db.sqlite"))
    services = Services(
        runtime=StubRuntime(),
        artifacts=StubArtifacts(),
        audit=AuditLoggerImpl(repository, settings),
        sovereignty=NullSovereignty(),
        policy=StubPolicy(),
        ml_tools=StubMlTools(),
        artifact_validator=StubArtifactValidator(),
        workspace_root=workspace_root,
    )
    services.runtime = ToolRuntimeImpl(settings, services)
    return services, StubOrchestrator(), StubRag(), StubPid()
