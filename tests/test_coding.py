from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.coding import CodingModel, CodingRepairLoop, CodingResultVerifier
from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext, ToolResult
from app.errors import ModelUnavailableError
from app.providers.types import InferenceResult, ModelInfo, ProviderHealth


class Provider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
    def is_local(self): return True
    def health_check(self): return ProviderHealth("ollama", True)
    def generate(self, model_id, messages, tools=None):
        self.calls += 1
        return InferenceResult(next(self.outputs), model_id, "ollama")


class Policy:
    def __init__(self, allowed=True): self.allowed, self.requests = allowed, []
    async def validate(self, ctx, request):
        self.requests.append(request)
        return PolicyDecision(allowed=self.allowed, tool=request.tool, validated_args=request.args, decision_id="d", reason="denied" if not self.allowed else None)


class Executor:
    def __init__(self, results): self.results, self.calls = iter(results), []
    async def execute(self, ctx, decision):
        self.calls.append(decision)
        return next(self.results)


def source(path="code/main.py"):
    return json.dumps({"path": path, "language": "python", "source": "print('ok')", "explanation": "test"})


def model(outputs, *, mode="local"):
    provider = Provider(outputs)
    info = ModelInfo("code", "code", "ollama", "local", frozenset({"coding"}), frozenset({"mac_silicon"}))
    router = ModelRouter(Settings(inference_mode=mode), ModelRegistry([info]), {"ollama": provider}, ResourceManager())  # type: ignore[arg-type]
    return CodingModel(router), provider


def result(ok=True, exit_code: int | None = 0, *, data=None, events=None, stderr=""):
    return ToolResult(ok=ok, tool="x", exit_code=exit_code, data=data or {}, stderr=stderr, resource_events=events or [])


def context():
    return TaskContext(task_id="t", task_type="coding", workspace=Path("."), inference_mode="local")


def test_model_router_selects_coding_model_and_generates_code():
    coding, provider = model([source()])
    generated = coding.generate("write a program")
    assert generated.path == "code/main.py"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_generated_code_becomes_policy_gated_tool_requests():
    coding, _ = model([source()])
    policy = Policy()
    executor = Executor([result(), result(), result(data={"passed": 1, "failed": 0})])
    passed, _ = await CodingRepairLoop(coding, policy, executor).run(context(), "write code")
    assert passed
    assert [request.tool for request in policy.requests] == ["create_code", "execute_code", "run_tests"]
    assert [decision.tool for decision in executor.calls] == ["create_code", "execute_code", "run_tests"]


@pytest.mark.parametrize(
    "failure",
    [
        result(False, 1, stderr="SyntaxError"),
        result(False, 1, data={"passed": 0, "failed": 1}),
        result(False, 1, stderr="RuntimeError"),
        result(False, None, events=["TIMEOUT"]),
        result(False, None, events=["OOM_KILLED"]),
    ],
)
def test_deterministic_execution_failure_interpretation(failure):
    assert not CodingResultVerifier().verify(failure).success


@pytest.mark.asyncio
async def test_successful_repair_and_three_failures_terminate():
    coding, _ = model([source(), source()])
    policy = Policy()
    executor = Executor([
        result(False, 1, stderr="SyntaxError"),
        result(), result(), result(data={"passed": 1, "failed": 0}),
    ])
    passed, attempts = await CodingRepairLoop(coding, policy, executor).run(context(), "write code")
    assert passed and len(attempts) == 2

    coding, _ = model([source(), source(), source()])
    executor = Executor([result(False, 1)] * 3)
    passed, attempts = await CodingRepairLoop(coding, Policy(), executor).run(context(), "write code")
    assert not passed and len(attempts) == 3


@pytest.mark.asyncio
async def test_denied_policy_prevents_execution():
    coding, _ = model([source()])
    executor = Executor([])
    passed, _ = await CodingRepairLoop(coding, Policy(False), executor).run(context(), "write code")
    assert not passed and executor.calls == []


def test_no_inference_mode_fallback():
    coding, _ = model([source()], mode="groq")
    with pytest.raises(ModelUnavailableError):
        coding.generate("write code")
