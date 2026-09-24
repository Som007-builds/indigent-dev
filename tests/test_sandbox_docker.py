import docker
import pytest
from docker.errors import DockerException, ImageNotFound

from app.config import Settings
from app.core.workspace import create_workspace
from app.runtime.sandbox import DockerSandbox


class Audit:
    def __init__(self) -> None:
        self.categories: list[str] = []

    async def emit(self, category: str, *_: object, **__: object) -> None:
        self.categories.append(category)


def _docker_or_skip(settings: Settings):
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(settings.sandbox_image)
        return client
    except (DockerException, ImageNotFound):
        pytest.skip("Docker daemon or indigent sandbox image is unavailable")


@pytest.mark.docker
@pytest.mark.asyncio
async def test_sandbox_selftest_and_network_block_audit(tmp_path):
    settings = Settings(data_dir=tmp_path)
    _docker_or_skip(settings)
    workspace = create_workspace(tmp_path / "workspaces", "task")
    audit = Audit()
    sandbox = DockerSandbox(settings, audit)
    selftest = await sandbox.run(workspace, ["python", "/opt/indigent-selftest.py"], "task")
    assert selftest.exit_code == 0
    code = workspace / "code" / "network.py"
    code.write_text("import socket\nsocket.create_connection(('1.1.1.1', 53), 1)\n", encoding="utf-8")
    result = await sandbox.run(workspace, ["python", "network.py"], "task")
    assert result.exit_code != 0 and "NETWORK_BLOCKED" in result.resource_events
    assert "SANDBOX_BLOCKED_NETWORK" in audit.categories
