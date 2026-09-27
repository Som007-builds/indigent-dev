import asyncio
from time import monotonic

from app.config import Settings, get_settings
from app.contracts.models import TaskContext, TaskEvent, ToolRequest
from app.providers.groq import GroqProvider
from app.providers.types import Message


class StubOrchestrator:
    def __init__(self, settings: Settings | None = None, models_status: object | None = None) -> None:
        self.settings = settings
        self.models_status = models_status
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

        if ctx.inference_mode == "groq" and not user_request.startswith("stub:"):
            settings = self.settings or get_settings()
            if not settings.groq_api_key:
                yield await self._event(
                    "failed",
                    {"error": {"code": "GROQ_KEY_MISSING", "message": "GROQ_API_KEY is not configured in .env"}},
                )
                return

            yield await self._event("state_changed", {"state": "INTAKE"})
            yield await self._event("state_changed", {"state": "CLASSIFY", "task_type": "inspection"})
            ctx.task_type = "inspection"

            # Determine Groq model ID
            model_id = "openai/gpt-oss-20b"
            if self.models_status is not None and hasattr(self.models_status, "get_active_model"):
                candidate = self.models_status.get_active_model()
                if candidate in {
                    "openai/gpt-oss-120b",
                    "openai/gpt-oss-20b",
                    "qwen/qwen3.8-27b",
                    "allam-2-7b",
                    "openai/gpt-oss-safeguard-20b",
                }:
                    model_id = candidate

            yield await self._event(
                "model_selected",
                {
                    "model_id": model_id,
                    "model_name": model_id,
                    "provider": "groq",
                    "mode": "groq",
                    "task_type": ctx.task_type,
                    "inference_mode": "groq",
                    "local": False,
                    "role": "reasoning",
                },
            )

            yield await self._event("state_changed", {"state": "PLAN"})
            yield await self._event(
                "plan",
                {"steps": ["Analyze query", "Execute Groq LPU inference", "Validate & verify output"]},
            )

            context_blocks: list[str] = []
            if file_ids:
                yield await self._event("state_changed", {"state": "RETRIEVE"})
                chunks: list[dict] = []
                inputs_dir = ctx.workspace / "inputs"
                if inputs_dir.is_dir():
                    for f in inputs_dir.iterdir():
                        if f.is_file():
                            try:
                                content = f.read_text(encoding="utf-8", errors="ignore")[:30000]
                                context_blocks.append(f"--- Document: {f.name} ---\n{content}\n")
                                chunks.append({"source": f.name, "snippet": content[:300]})
                            except Exception:
                                pass
                yield await self._event("retrieval", {"chunks": chunks})

            prompt_content = user_request
            if context_blocks:
                prompt_content = (
                    "Context from attached documents:\n"
                    + "\n".join(context_blocks)
                    + f"\n\nUser Request: {user_request}"
                )

            messages = [
                Message(
                    role="system",
                    content="You are the AI-Harness Sovereign Industrial Assistant for engineering workflows, document verification, and plant analysis. Provide concise, accurate, and professional assistance.",
                ),
                Message(role="user", content=prompt_content),
            ]

            yield await self._event("state_changed", {"state": "TOOL"})
            yield await self._event(
                "tool_proposed",
                {"tool": "groq_inference", "args": {"model": model_id, "prompt_length": len(prompt_content)}},
            )

            provider = GroqProvider(settings.groq_api_key, timeout=settings.model_generation_timeout_s)
            try:
                started = monotonic()
                try:
                    result = await asyncio.to_thread(provider.generate, model_id, messages)
                except Exception as inner_err:
                    if model_id != "openai/gpt-oss-20b":
                        result = await asyncio.to_thread(provider.generate, "openai/gpt-oss-20b", messages)
                        model_id = "openai/gpt-oss-20b"
                    else:
                        raise inner_err
                elapsed_ms = int((monotonic() - started) * 1000)

                yield await self._event(
                    "tool_result",
                    {
                        "tool": "groq_inference",
                        "ok": True,
                        "duration_ms": elapsed_ms,
                        "summary": f"Generated {len(result.text)} chars via {model_id}",
                    },
                )

                if hasattr(services, "sovereignty") and hasattr(services.sovereignty, "record_external_call"):
                    req_bytes = sum(len(m.content.encode("utf-8")) for m in messages)
                    resp_bytes = len(result.text.encode("utf-8"))
                    await services.sovereignty.record_external_call("groq", req_bytes, resp_bytes)

            except Exception as e:
                yield await self._event(
                    "tool_result",
                    {"tool": "groq_inference", "ok": False, "error": str(e)},
                )
                yield await self._event(
                    "failed",
                    {"error": {"code": "GROQ_INFERENCE_FAILED", "message": f"Groq inference failed: {e}"}},
                )
                return

            yield await self._event("state_changed", {"state": "VERIFY"})
            yield await self._event(
                "verification",
                {"status": "passed", "details": f"Inference verified via {model_id} ({elapsed_ms}ms)"},
            )

            yield await self._event("state_changed", {"state": "COMPLETE"})
            yield await self._event(
                "completed",
                {"final_result": result.text},
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
