import asyncio

from app.contracts.models import TaskContext, TaskEvent, ToolRequest


class StubOrchestrator:
    def __init__(self) -> None:
        self._approvals: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, str] = {}

    async def approve(self, task_id: str, approver: str, decision: str, note: str | None) -> None:
        self._decisions[task_id] = decision
        self._approvals.setdefault(task_id, asyncio.Event()).set()

    async def _event(self, event_type: str, data: dict = {}) -> TaskEvent:
        await asyncio.sleep(0.05)
        return TaskEvent(type=event_type, data=data)

    async def run(self, ctx: TaskContext, user_request: str, file_ids: list[str], services: object):
        if user_request.startswith("stub:slow"):
            await asyncio.sleep(400)
            return
        if user_request.startswith("stub:fail"):
            yield await self._event(
                "failed", {"error": {"code": "STUB_FAILURE", "message": "Requested failure"}}
            )
            return
        yield await self._event("state_changed", {"state": "INTAKE"})
        yield await self._event("state_changed", {"state": "CLASSIFY", "task_type": "inspection"})
        ctx.task_type = "inspection"
        yield await self._event("plan", {"steps": ["Inspect input", "Create report"]})
        yield await self._event("state_changed", {"state": "RETRIEVE"})
        yield await self._event("retrieval", {"chunks": []})
        if user_request.startswith("stub:tool"):
            request = ToolRequest(tool="read_file", args={})
            decision = await services.policy.validate(ctx, request)
            yield await self._event("tool_proposed", {"tool": request.tool, "args": request.args})
            yield await self._event("policy_decision", decision.model_dump())
            result = await services.runtime.execute(ctx, decision)
            yield await self._event(
                "tool_result",
                {
                    "tool": result.tool,
                    "ok": result.ok,
                    "summary": "stub",
                    "duration_ms": result.duration_ms,
                },
            )
        yield await self._event("state_changed", {"state": "VERIFY"})
        yield await self._event("verification", {"status": "passed", "details": "stub"})
        yield await self._event("state_changed", {"state": "ARTIFACT"})
        manifest = await services.artifacts.create_stub_docx(ctx)
        yield await self._event(
            "artifact_created",
            {"artifact_id": manifest.artifact_id, "artifact_type": manifest.artifact_type},
        )
        yield await self._event("state_changed", {"state": "ARTIFACT_VALIDATE"})
        report = await services.artifact_validator.validate(manifest)
        yield await self._event(
            "artifact_validation",
            {"artifact_id": manifest.artifact_id, "passed": report.passed, "checks": report.checks},
        )
        yield await self._event(
            "approval_requested",
            {"artifact_ids": [manifest.artifact_id], "summary": "Stub artifact"},
        )
        if user_request.startswith("stub:hang_approval"):
            await asyncio.Event().wait()
        event = self._approvals.setdefault(ctx.task_id, asyncio.Event())
        await event.wait()
        if self._decisions.get(ctx.task_id) == "reject":
            yield await self._event(
                "failed", {"error": {"code": "REJECTED", "message": "Rejected"}}
            )
            return
        yield await self._event("completed", {"final_result": "Stub task complete"})
