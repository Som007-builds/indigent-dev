import asyncio
from time import monotonic
from typing import Any

from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext, ToolResult
from app.errors import SandboxUnavailableError, ToolNotAllowedError
from app.runtime.registry import ToolRegistry, validate, validate_paths
from app.runtime.sandbox import DockerSandbox
from app.stubs.policy import ALLOWED_TOOLS


class ToolRuntimeImpl:
    def __init__(self, settings: Settings, services: Any) -> None:
        self.settings, self.services = settings, services
        self.registry = ToolRegistry(DockerSandbox(settings, services.audit), services)

    async def execute(self, ctx: TaskContext, decision: PolicyDecision) -> ToolResult:
        started = monotonic()
        if not decision.allowed:
            await self._audit("POLICY_DENIED", ctx, decision.tool, "denied", {}, 0, [])
            raise ToolNotAllowedError(decision.reason or "Policy did not allow this tool")
        if decision.tool not in ALLOWED_TOOLS.get(ctx.task_type or "", set()):
            await self._audit("POLICY_DENIED", ctx, decision.tool, "denied", {}, 0, [])
            raise ToolNotAllowedError("Tool is not allowed for this task type")
        args: dict = {}
        events: list[str] = []
        try:
            args = validate_paths(ctx, decision.tool, validate(decision.tool, decision.validated_args))
            result = await asyncio.wait_for(self.registry.run(ctx, decision.tool, args), self.settings.per_tool_timeout_s)
            events = result.resource_events
        except (ToolNotAllowedError, SandboxUnavailableError):
            raise
        except Exception as exc:
            result = ToolResult(ok=False, tool=decision.tool, error=_clean_error(exc))
        result.duration_ms = result.duration_ms or int((monotonic() - started) * 1000)
        await self._audit("TOOL_EXECUTED", ctx, decision.tool, "ok" if result.ok else "error", args, result.duration_ms, events)
        return result

    async def _audit(self, category: str, ctx: TaskContext, tool: str, status: str, args: dict, duration: int, events: list[str]) -> None:
        sizes = {key: len(str(value)) for key, value in args.items()}
        await self.services.audit.emit(category, "runtime", tool, status, ctx.task_id, {"tool": tool, "arg_names": list(args), "arg_sizes": sizes, "duration_ms": duration, "resource_events": events})


def _clean_error(exc: Exception) -> str:
    return exc.message if hasattr(exc, "message") else "Tool execution failed"
