from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext
from app.core.workspace import create_workspace
from app.errors import SandboxUnavailableError, ToolNotAllowedError
from app.runtime.executor import ToolRuntimeImpl
from app.runtime.sandbox import DockerSandbox


class Audit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def emit(self, category: str, component: str, action: str, status: str = "info", task_id: str | None = None, details: dict | None = None) -> None:
        self.entries.append({"category": category, "status": status, "details": details or {}})


@pytest.fixture
def runtime(tmp_path):
    audit = Audit()
    services = SimpleNamespace(audit=audit, artifacts=None, ml_tools=None)
    ctx = TaskContext(task_id="task", task_type="coding", workspace=create_workspace(tmp_path / "workspaces", "task"), inference_mode="local")
    return ToolRuntimeImpl(Settings(data_dir=tmp_path), services), ctx, audit


@pytest.mark.asyncio
async def test_policy_denial_never_reaches_runtime(runtime):
    implementation, ctx, audit = runtime
    with pytest.raises(ToolNotAllowedError):
        await implementation.execute(ctx, PolicyDecision(allowed=False, tool="write_file", decision_id="d"))
    assert audit.entries[0]["category"] == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_unknown_and_wrong_task_tools_are_refused(runtime):
    implementation, ctx, audit = runtime
    for tool in ("unknown", "create_docx"):
        with pytest.raises(ToolNotAllowedError):
            await implementation.execute(ctx, PolicyDecision(allowed=True, tool=tool, decision_id="d"))
    assert [item["category"] for item in audit.entries] == ["POLICY_DENIED", "POLICY_DENIED"]


@pytest.mark.asyncio
async def test_invalid_paths_and_extra_arguments_do_not_execute(runtime):
    implementation, ctx, audit = runtime
    bad_path = PolicyDecision(allowed=True, tool="write_file", decision_id="d", validated_args={"path": "../x.py", "content": "x"})
    result = await implementation.execute(ctx, bad_path)
    assert not result.ok and not list(ctx.workspace.rglob("x.py"))
    extra = PolicyDecision(allowed=True, tool="write_file", decision_id="d", validated_args={"path": "code/x.py", "content": "x", "extra": True})
    result = await implementation.execute(ctx, extra)
    assert not result.ok and not (ctx.workspace / "code" / "x.py").exists()
    assert [item["category"] for item in audit.entries] == ["TOOL_EXECUTED", "TOOL_EXECUTED"]


@pytest.mark.asyncio
async def test_write_file_uses_validated_workspace_path(runtime):
    implementation, ctx, _ = runtime
    result = await implementation.execute(ctx, PolicyDecision(allowed=True, tool="write_file", decision_id="d", validated_args={"path": "code/main.py", "content": "print('safe')"}))
    assert result.ok
    assert (ctx.workspace / "code" / "main.py").read_text(encoding="utf-8") == "print('safe')"


@pytest.mark.asyncio
async def test_unavailable_docker_fails_closed(monkeypatch, tmp_path):
    import docker
    from docker.errors import DockerException

    class MissingDocker:
        def ping(self):
            raise DockerException("unavailable")

    monkeypatch.setattr(docker, "from_env", lambda: MissingDocker())
    with pytest.raises(SandboxUnavailableError):
        await DockerSandbox(Settings(data_dir=tmp_path), Audit()).run(
            create_workspace(tmp_path / "workspaces", "task"), ["python", "-V"], "task"
        )
