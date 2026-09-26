from __future__ import annotations

import asyncio

import pytest

from app.agent.orchestrator import (
    MAX_REPAIR_ATTEMPTS,
    BoundedOrchestrator,
    OrchestratorDependencies,
)
from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.artifact_validation import ArtifactValidationContext, ArtifactValidationResult
from app.config import Settings
from app.contracts.models import ArtifactManifest, PolicyDecision, TaskContext
from app.providers.types import InferenceResult, ModelInfo, ProviderHealth, ToolSchema


class Provider:
    def is_local(self) -> bool:
        return True

    def health_check(self) -> ProviderHealth:
        return ProviderHealth("ollama", True)

    def generate(self, model_id, messages, tools=None):
        return InferenceResult("", model_id, "ollama")


class Planner:
    def __init__(self, task_type="inspection", plan_steps=None, delay=0):
        self.task_type = task_type
        self.plan_steps = plan_steps or ["read_file"]
        self.delay = delay

    async def classify(self, request, model_id, provider):
        await asyncio.sleep(self.delay)
        return self.task_type

    async def plan(self, request, task_type, tools, model_id, provider):
        await asyncio.sleep(self.delay)
        return self.plan_steps


class Tools:
    def __init__(self, delay=0):
        self.delay = delay
        self.calls = 0

    async def execute(self, decision):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return {"tool": decision.tool, "ok": True}


class Policy:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = 0

    async def validate(self, ctx, request):
        self.calls += 1
        return PolicyDecision(
            allowed=self.allowed,
            tool=request.tool,
            validated_args=request.args,
            decision_id="decision",
            reason=None if self.allowed else "denied",
        )


class Verify:
    def __init__(self, results):
        self.results = iter(results)

    async def verify(self, task):
        result = next(self.results)
        return result, "check"


class Artifacts:
    def __init__(self, valid=True):
        self.valid = valid

    async def create(self, task):
        return [{"artifact_id": "a1"}]

    async def validate(self, task):
        return self.valid, [{"name": "content", "passed": self.valid}]


def make_orchestrator(planner=None, tools=None, verifier=None, artifacts=None, policy=None, **kwargs):
    model = ModelInfo(
        "local-model", "local-model", "ollama", "local", frozenset({"inspection", "coding"}),
        frozenset({"mac_silicon"}), memory_estimate_mb=0,
    )
    router = ModelRouter(
        Settings(), ModelRegistry([model]), {"ollama": Provider()}, ResourceManager()
    )
    deps = OrchestratorDependencies(
        planner or Planner(), tools or Tools(), verifier or Verify([True]), artifacts or Artifacts(),
        policy or Policy(), tools=(ToolSchema("read_file"),),
        approval=kwargs.pop("approval", lambda task: asyncio.sleep(0, result=True)),
        artifact_validator=kwargs.pop("artifact_validator", None),
        artifact_manifests=kwargs.pop("artifact_manifests", ()),
        artifact_validation_context=kwargs.pop("artifact_validation_context", ArtifactValidationContext()),
        artifact_repair=kwargs.pop("artifact_repair", None),
    )
    return BoundedOrchestrator(router, deps, **kwargs)


def context(task_id="task"):
    from pathlib import Path
    return TaskContext(task_id=task_id, task_type=None, workspace=Path("."), inference_mode="local")


async def events(orchestrator):
    return [event async for event in orchestrator.run(context(), "request", [])]


@pytest.mark.asyncio
async def test_successful_completion_and_valid_transitions():
    result = await events(make_orchestrator(approval=lambda task: asyncio.sleep(0, result=True)))
    assert result[-1].type == "completed"
    assert [event.data.get("state") for event in result if event.type == "state_changed"] == [
        "INTAKE", "CLASSIFY", "PLAN", "TOOL", "VERIFY", "ARTIFACT", "ARTIFACT_VALIDATE", "APPROVAL"
    ]


@pytest.mark.asyncio
async def test_repair_loop_is_bounded_at_three_attempts():
    result = await events(make_orchestrator(verifier=Verify([False, False, False]), approval=lambda task: asyncio.sleep(0, result=True)))
    assert result[-1].data["error"]["code"] == "VERIFICATION_FAILED"
    assert len([event for event in result if event.type == "repair"]) == MAX_REPAIR_ATTEMPTS - 1


@pytest.mark.asyncio
async def test_verification_failure_can_repair_then_complete():
    orchestrator = make_orchestrator(verifier=Verify([False, True]), approval=lambda task: asyncio.sleep(0, result=True))
    result = await events(orchestrator)
    assert result[-1].type == "completed"
    assert any(event.type == "repair" for event in result)


@pytest.mark.asyncio
async def test_artifact_validation_failure_is_clean():
    result = await events(make_orchestrator(artifacts=Artifacts(False), approval=lambda task: asyncio.sleep(0, result=True)))
    assert result[-1].data["error"]["code"] == "ARTIFACT_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_task_timeout():
    result = await events(make_orchestrator(tools=Tools(delay=1), task_timeout_s=0.01))
    assert result[-1].data["error"]["code"] == "TASK_TIMEOUT"


@pytest.mark.asyncio
async def test_tool_timeout():
    result = await events(make_orchestrator(tools=Tools(delay=1), tool_timeout_s=0.01))
    assert result[-1].data["error"]["code"] == "TOOL_TIMEOUT"


@pytest.mark.asyncio
async def test_model_generation_timeout():
    result = await events(make_orchestrator(planner=Planner(delay=1), model_timeout_s=0.01))
    assert result[-1].data["error"]["code"] == "TASK_TIMEOUT"


@pytest.mark.asyncio
async def test_router_mode_is_preserved_without_switching():
    result = await events(make_orchestrator())
    selected = next(event for event in result if event.type == "model_selected")
    assert selected.data["provider"] == "ollama"


@pytest.mark.asyncio
async def test_artifact_validator_invalid_without_repair_callback_fails_cleanly():
    class Validator:
        async def validate(self, manifest, context=None):
            return ArtifactValidationResult("INVALID", False, "hash", ({"name": "bad", "passed": False},))

    manifest = ArtifactManifest(
        artifact_id="a1", task_id="task", artifact_type="docx", path="unused.docx",
        created_at="2026-09-25T10:00:00Z", artifact_hash="hash",
    )
    events = await events_for_artifact_validator(Validator(), manifest)
    assert [event.data.get("state") for event in events if event.type == "state_changed"][-1] == "ARTIFACT_VALIDATE"
    assert any(event.type == "repair" for event in events)
    assert events[-1].data["error"]["code"] == "ARTIFACT_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_artifact_validator_valid_proceeds_to_approval_and_complete():
    class Validator:
        async def validate(self, manifest, context=None):
            return ArtifactValidationResult("VALID", True, "hash", ())

    manifest = ArtifactManifest(
        artifact_id="a1", task_id="task", artifact_type="docx", path="unused.docx",
        created_at="2026-09-25T10:00:00Z", artifact_hash="hash",
    )
    result = await events_for_artifact_validator(Validator(), manifest)
    assert any(event.data.get("state") == "APPROVAL" for event in result if event.type == "state_changed")
    assert result[-1].type == "completed"


async def events_for_artifact_validator(validator, manifest, artifact_repair=None):
    orchestrator = make_orchestrator(
        artifact_validator=validator,
        artifact_manifests=(manifest,),
        artifact_repair=artifact_repair,
    )
    return await events(orchestrator)


@pytest.mark.asyncio
async def test_invalid_artifact_is_repaired_and_revalidated_then_completes():
    class Validator:
        def __init__(self):
            self.results = iter([
                ArtifactValidationResult("INVALID", False, "bad-hash", ({"name": "content", "passed": False},)),
                ArtifactValidationResult("VALID", True, "good-hash", ()),
            ])

        async def validate(self, manifest, context=None):
            return next(self.results)

    class Repair:
        def __init__(self):
            self.results = []

        async def __call__(self, task, validation):
            self.results.append(validation)
            return ArtifactManifest(
                artifact_id="a1", task_id="task", artifact_type="docx", path="repaired.docx",
                created_at="2026-09-25T10:00:00Z", artifact_hash="repaired-hash",
            )

    repair = Repair()
    manifest = ArtifactManifest(
        artifact_id="a1", task_id="task", artifact_type="docx", path="unused.docx",
        created_at="2026-09-25T10:00:00Z", artifact_hash="hash",
    )
    result = await events_for_artifact_validator(Validator(), manifest, repair)
    assert result[-1].type == "completed", result[-1].data
    assert len(repair.results) == 1
    assert repair.results[0].status == "INVALID"
    assert [event.data.get("state") for event in result if event.type == "state_changed"].count("ARTIFACT_VALIDATE") == 2


@pytest.mark.asyncio
async def test_unverified_artifact_is_repaired_and_revalidated():
    class Validator:
        def __init__(self):
            self.results = iter([
                ArtifactValidationResult("UNVERIFIED", False, "hash-1", ({"name": "structure", "passed": None},)),
                ArtifactValidationResult("VALID", True, "hash-2", ()),
            ])

        async def validate(self, manifest, context=None):
            return next(self.results)

    received = []

    async def repair(task, validation):
        received.append(validation)
        return ArtifactManifest(
            artifact_id="a1", task_id="task", artifact_type="docx", path="repaired.docx",
            created_at="2026-09-25T10:00:00Z", artifact_hash="repaired-hash",
        )

    manifest = ArtifactManifest(
        artifact_id="a1", task_id="task", artifact_type="docx", path="unused.docx",
        created_at="2026-09-25T10:00:00Z", artifact_hash="hash",
    )
    result = await events_for_artifact_validator(Validator(), manifest, repair)
    assert result[-1].type == "completed", result[-1].data
    assert received[0].status == "UNVERIFIED"
    assert any(event.data.get("status") == "UNVERIFIED" for event in result if event.type == "artifact_validation")


@pytest.mark.asyncio
async def test_artifact_repair_uses_shared_limit_and_preserves_last_result():
    class Validator:
        def __init__(self):
            self.calls = 0

        async def validate(self, manifest, context=None):
            self.calls += 1
            return ArtifactValidationResult(
                "INVALID", False, f"hash-{self.calls}", ({"name": "content", "passed": False},)
            )

    class Repair:
        def __init__(self):
            self.calls = 0

        async def __call__(self, task, validation):
            self.calls += 1
            assert validation.status == "INVALID"
            return ArtifactManifest(
                artifact_id="a1", task_id="task", artifact_type="docx", path="repaired.docx",
                created_at="2026-09-25T10:00:00Z", artifact_hash="repaired-hash",
            )

    validator = Validator()
    repair = Repair()
    manifest = ArtifactManifest(
        artifact_id="a1", task_id="task", artifact_type="docx", path="unused.docx",
        created_at="2026-09-25T10:00:00Z", artifact_hash="hash",
    )
    orchestrator = make_orchestrator(
        artifact_validator=validator,
        artifact_manifests=(manifest,),
        artifact_repair=repair,
    )
    result = await events(orchestrator)
    assert result[-1].data["error"]["code"] == "ARTIFACT_VALIDATION_FAILED"
    assert repair.calls == MAX_REPAIR_ATTEMPTS
    assert validator.calls == MAX_REPAIR_ATTEMPTS + 1
    assert orchestrator._last_task_snapshot is not None
    assert orchestrator._last_task_snapshot.artifact_validation_result.status == "INVALID"


@pytest.mark.asyncio
async def test_orchestrator_cannot_bypass_denied_policy():
    tools = Tools()
    policy = Policy(False)
    result = await events(make_orchestrator(tools=tools, policy=policy))
    assert result[-1].data["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert policy.calls == 1 and tools.calls == 0
