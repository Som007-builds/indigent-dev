import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound

from app.config import Settings
from app.errors import SandboxUnavailableError


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    truncated: bool
    resource_events: list[str]


class DockerSandbox:
    def __init__(self, settings: Settings, audit: Any) -> None:
        self.settings, self.audit = settings, audit

    async def run(self, workspace: Path, command: list[str], task_id: str) -> SandboxResult:
        return await asyncio.to_thread(self._run, workspace, command, task_id)

    def _run(self, workspace: Path, command: list[str], task_id: str) -> SandboxResult:
        container = None
        started = monotonic()
        try:
            client = docker.from_env()
            try:
                client.ping()
                client.images.get(self.settings.sandbox_image)
            except (DockerException, ImageNotFound) as exc:
                raise SandboxUnavailableError() from exc
            code = (workspace / "code").resolve()
            container = client.containers.run(
                self.settings.sandbox_image,
                command=command,
                detach=True,
                network_mode="none",
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                pids_limit=self.settings.sandbox_pids,
                mem_limit=f"{self.settings.sandbox_mem_mb}m",
                memswap_limit=f"{self.settings.sandbox_mem_mb}m",
                nano_cpus=int(self.settings.sandbox_cpus * 1_000_000_000),
                user="10001:10001",
                volumes={str(code): {"bind": "/work", "mode": "rw"}},
                working_dir="/work",
                auto_remove=False,
            )
            asyncio.run(self.audit.emit("SANDBOX_STARTED", "sandbox", "container started", "info", task_id))
            try:
                result = container.wait(timeout=self.settings.per_tool_timeout_s)
                exit_code = int(result.get("StatusCode", 1))
                events: list[str] = []
            except Exception as exc:
                if not _is_timeout(exc):
                    raise SandboxUnavailableError() from exc
                container.kill()
                exit_code, events = None, ["TIMEOUT"]
            container.reload()
            state = container.attrs.get("State", {})
            if state.get("OOMKilled"):
                events.append("OOM_KILLED")
            limit = self.settings.sandbox_output_limit_kb * 1024
            stdout, stderr, stdout_cut, stderr_cut = _logs(container, limit)
            if stdout_cut or stderr_cut:
                events.append("OUTPUT_TRUNCATED")
            if "can't start new thread" in stderr or "Resource temporarily unavailable" in stderr:
                events.append("PIDS_LIMIT")
            if any(s in stderr for s in ("Network is unreachable", "Name or service not known", "Temporary failure in name resolution")):
                events.append("NETWORK_BLOCKED")
                asyncio.run(self.audit.emit("SANDBOX_BLOCKED_NETWORK", "sandbox", "network blocked", "denied", task_id))
            return SandboxResult(stdout, stderr, exit_code, int((monotonic() - started) * 1000), stdout_cut or stderr_cut, events)
        except SandboxUnavailableError:
            raise
        except DockerException as exc:
            raise SandboxUnavailableError() from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass


def _is_timeout(exc: Exception) -> bool:
    return "timeout" in str(exc).lower()


def _logs(container: Any, limit: int) -> tuple[str, str, bool, bool]:
    def collect(stdout: bool, stderr: bool) -> tuple[str, bool]:
        chunks, size, truncated = [], 0, False
        for chunk in container.logs(stdout=stdout, stderr=stderr, stream=True):
            remaining = limit - size
            if remaining <= 0:
                truncated = True
                continue
            chunks.append(chunk[:remaining])
            size += min(len(chunk), remaining)
            truncated = truncated or len(chunk) > remaining
        return b"".join(chunks).decode("utf-8", "replace"), truncated

    stdout, stdout_cut = collect(True, False)
    stderr, stderr_cut = collect(False, True)
    return stdout, stderr, stdout_cut, stderr_cut
