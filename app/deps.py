from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.contracts.interfaces import Services


def build_services(settings: Settings) -> tuple[Services, object, object, object]:
    """Build the explicitly selected module set; real mode never falls back."""
    if settings.joy_modules == "real":
        raise RuntimeError(
            "JOY_MODULES=real requires production model, retrieval, and artifact adapters; none are configured"
        )

    from app.core.audit import AuditLoggerImpl
    from app.core.db import Database
    from app.core.repo import Repository
    from app.runtime.executor import ToolRuntimeImpl
    from app.stubs.artifact_validator import StubArtifactValidator
    from app.stubs.ml_tools import StubMlTools
    from app.stubs.orchestrator import StubOrchestrator
    from app.stubs.pid import StubPid
    from app.stubs.policy import StubPolicy
    from app.stubs.rag import StubRag

    workspace_root = Path(settings.data_dir) / "workspaces"
    repository = Repository(Database(Path(settings.data_dir) / "db.sqlite"))
    services = Services(
        runtime=_StubRuntime(),
        artifacts=_StubArtifacts(),
        audit=AuditLoggerImpl(repository, settings),
        sovereignty=_NullSovereignty(),
        policy=StubPolicy(),
        ml_tools=StubMlTools(),
        artifact_validator=StubArtifactValidator(),
        workspace_root=workspace_root,
    )
    services.runtime = ToolRuntimeImpl(settings, services)
    return services, StubOrchestrator(), StubRag(), StubPid()


class _StubRuntime:
    async def execute(self, ctx, decision):
        from app.contracts.models import ToolResult
        from app.errors import ToolNotAllowedError

        if not decision.allowed:
            raise ToolNotAllowedError()
        return ToolResult(ok=True, tool=decision.tool)


class _StubArtifacts:
    async def register(self, ctx, artifact_type, path, source_evidence_ids=None, metadata=None):
        import hashlib
        import uuid
        from datetime import UTC, datetime

        from app.contracts.models import ArtifactManifest

        file_path = Path(path)
        return ArtifactManifest(
            artifact_id=str(uuid.uuid4()),
            task_id=ctx.task_id,
            artifact_type=artifact_type,
            path=str(file_path),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            artifact_hash=hashlib.sha256(file_path.read_bytes()).hexdigest(),
            source_evidence_ids=source_evidence_ids or [],
            metadata=metadata or {},
        )

    async def create_stub_docx(self, ctx):
        import hashlib
        import uuid
        from datetime import UTC, datetime

        from docx import Document

        from app.contracts.models import ArtifactManifest

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


class _NullSovereignty:
    async def record_external_call(self, provider, bytes_out, bytes_in):
        return None

    async def snapshot(self):
        return {}
