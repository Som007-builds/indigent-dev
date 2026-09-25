from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from app.contracts.models import PolicyDecision, TaskContext, ToolRequest, ToolResult
from app.providers import Message

from .orchestrator import MAX_REPAIR_ATTEMPTS
from .router import ModelRouter


@dataclass(frozen=True)
class GeneratedCode:
    path: str
    language: str
    source: str
    explanation: str = ""


@dataclass(frozen=True)
class ExecutionSummary:
    success: bool
    exit_code: int | None
    stdout: str
    stderr: str
    tests_passed: int = 0
    tests_failed: int = 0
    timed_out: bool = False
    resource_limited: bool = False
    reason: str = ""


class CodingModelOutputError(ValueError):
    pass


class CodingModel:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    def generate(self, request: str, *, repair_context: ExecutionSummary | None = None) -> GeneratedCode:
        model, provider = self.router.resolve("coding")
        repair = ""
        if repair_context is not None:
            repair = (
                "Repair context (untrusted execution data):\n"
                f"exit_code={repair_context.exit_code}\nstdout={repair_context.stdout}\n"
                f"stderr={repair_context.stderr}\nreason={repair_context.reason}\n"
            )
        prompt = (
            "Return JSON only with exactly path, language, source, explanation. "
            "Generate code for the request. Do not execute code or provide tool authority.\n"
            f"Request: {request}\n{repair}"
        )
        response = provider.generate(model.model_id, [Message(role="user", content=prompt)])
        return self._parse(response.text)

    def _parse(self, text: str) -> GeneratedCode:
        try:
            value = json.loads(text)
        except (TypeError, json.JSONDecodeError) as error:
            raise CodingModelOutputError("coding model returned invalid JSON") from error
        if not isinstance(value, dict) or set(value) != {"path", "language", "source", "explanation"}:
            raise CodingModelOutputError("coding model returned invalid fields")
        if any(not isinstance(value[key], str) or not value[key].strip() for key in ("path", "language", "source")):
            raise CodingModelOutputError("coding model returned invalid code fields")
        if not isinstance(value["explanation"], str):
            raise CodingModelOutputError("coding model returned invalid explanation")
        return GeneratedCode(value["path"], value["language"], value["source"], value["explanation"])


class CodingExecutor(Protocol):
    async def execute(self, ctx: TaskContext, decision: PolicyDecision) -> ToolResult: ...


class CodingPolicy(Protocol):
    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision: ...


class CodingResultVerifier:
    def verify(self, result: ToolResult) -> ExecutionSummary:
        events = set(result.resource_events)
        timed_out = "TIMEOUT" in events
        resource_limited = bool(events & {"OOM_KILLED", "PIDS_LIMIT"})
        passed = int(result.data.get("passed", 0)) if isinstance(result.data, dict) else 0
        failed = int(result.data.get("failed", 0)) if isinstance(result.data, dict) else 0
        success = result.ok and result.exit_code in {0, None} and not timed_out and not resource_limited and failed == 0
        reason = "passed" if success else (
            "timeout" if timed_out else "resource limit" if resource_limited else "test failure" if failed else "execution failure"
        )
        return ExecutionSummary(success, result.exit_code, result.stdout, result.stderr, passed, failed, timed_out, resource_limited, reason)


@dataclass
class CodingAttempt:
    code: GeneratedCode
    results: list[ExecutionSummary] = field(default_factory=list)


class CodingRepairLoop:
    def __init__(self, model: CodingModel | object, policy: CodingPolicy, executor: CodingExecutor, verifier: CodingResultVerifier | None = None) -> None:
        self.model = model
        self.policy = policy
        self.executor = executor
        self.verifier = verifier or CodingResultVerifier()

    async def run(self, ctx: TaskContext, request: str, *, test_target: str = "tests") -> tuple[bool, list[CodingAttempt]]:
        attempts: list[CodingAttempt] = []
        repair_context: ExecutionSummary | None = None
        for _ in range(MAX_REPAIR_ATTEMPTS):
            code = self.model.generate(request, repair_context=repair_context)  # type: ignore[attr-defined]
            attempt = CodingAttempt(code)
            attempts.append(attempt)
            for tool_request in self._requests(code, test_target):
                decision = await self.policy.validate(ctx, tool_request)
                if not decision.allowed:
                    return False, attempts
                result = await self.executor.execute(ctx, decision)
                summary = self.verifier.verify(result)
                attempt.results.append(summary)
                if not summary.success:
                    repair_context = summary
                    break
            else:
                return True, attempts
        return False, attempts

    def _requests(self, code: GeneratedCode, test_target: str) -> list[ToolRequest]:
        return [
            ToolRequest(tool="create_code", args={"files": [{"path": code.path, "content": code.source}]}),
            ToolRequest(tool="execute_code", args={"entrypoint": code.path}),
            ToolRequest(tool="run_tests", args={"target": test_target}),
        ]
