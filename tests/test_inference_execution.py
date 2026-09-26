from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.agent.inference import RoutedInferenceExecutor
from app.agent.orchestrator import BoundedOrchestrator, OrchestratorDependencies, RoutedPlanner
from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager, ResourceSnapshot
from app.agent.router import ModelRouter
from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext
from app.providers.types import (
    ImageInput,
    InferenceResult,
    Message,
    ModelInfo,
    ProviderHealth,
    ToolSchema,
)


class Hardware:
    def snapshot(self):
        return ResourceSnapshot(vram_mb_available=100, ram_mb_available=100)


class FakeSovereignty:
    def __init__(self):
        self.calls = []

    async def record_external_call(self, provider, bytes_out, bytes_in):
        self.calls.append((provider, bytes_out, bytes_in))

    async def snapshot(self):
        return {}


class FakeAudit:
    def __init__(self):
        self.events = []
        self.fail = False

    async def emit(self, *args, **kwargs):
        self.events.append((args, kwargs))
        if self.fail:
            raise RuntimeError("audit unavailable")


class FakeProvider:
    def __init__(self, provider="ollama", *, delay=0, failure=None):
        self.provider = provider
        self.delay = delay
        self.failure = failure
        self.started = threading.Event()

    def generate_with_images(self, model_id, messages, images, tools=None):
        if self.failure:
            raise self.failure
        assert images
        return InferenceResult("image answer", model_id, self.provider)

    def is_local(self):
        return self.provider == "ollama"

    def health_check(self):
        return ProviderHealth(self.provider, True)

    def generate(self, model_id, messages, tools=None):
        self.started.set()
        if self.delay:
            time.sleep(self.delay)
        if self.failure:
            raise self.failure
        return InferenceResult("answer", model_id, self.provider)


def model(mode="local", memory=40):
    provider = "ollama" if mode == "local" else "groq"
    return ModelInfo(
        f"{mode}-m", f"{mode}-m", provider, mode,
        frozenset({"inspection"}), frozenset({"mac_silicon"}) if mode == "local" else frozenset(),
        memory_estimate_mb=memory,
    )


def make_executor(item, provider, *, manager=None, sovereignty=None, audit=None):
    manager = manager or ResourceManager(Hardware(), max_concurrency=1)
    sovereignty = sovereignty or FakeSovereignty()
    executor = RoutedInferenceExecutor(manager, sovereignty, item.mode, audit)
    return executor, manager, sovereignty


@pytest.mark.asyncio
async def test_resource_admission_happens_before_provider_and_metadata_is_returned():
    item = model()
    provider = FakeProvider()
    executor, manager, _ = make_executor(item, provider)
    execution = await executor.generate(item, provider, [Message("user", "hello")])
    assert provider.started.is_set()
    assert execution.metadata.provider == "ollama"
    assert execution.metadata.model_id == item.model_id
    assert execution.metadata.mode == "local"
    assert execution.metadata.local and execution.metadata.success
    assert manager.residency(item.model_id).active_requests == 0
    assert manager.residency(item.model_id).loaded


@pytest.mark.asyncio
async def test_resource_admission_failure_prevents_generation():
    item = model()
    provider = FakeProvider()
    manager = ResourceManager(Hardware(), max_concurrency=1)
    await manager.load(item)
    # Capacity is now fully reserved by residency; another larger model cannot fit.
    too_large = ModelInfo(
        "large", "large", "ollama", "local", frozenset({"inspection"}),
        frozenset({"mac_silicon"}), memory_estimate_mb=101,
    )
    executor = RoutedInferenceExecutor(manager, FakeSovereignty(), "local")
    with pytest.raises(RuntimeError, match="resources unavailable"):
        await executor.generate(too_large, provider, [Message("user", "hello")])
    assert not provider.started.is_set()


@pytest.mark.asyncio
async def test_resource_state_released_after_provider_failure():
    item = model()
    provider = FakeProvider(failure=OSError("provider down"))
    executor, manager, _ = make_executor(item, provider)
    with pytest.raises(OSError, match="provider down"):
        await executor.generate(item, provider, [Message("user", "hello")])
    assert manager.residency(item.model_id).active_requests == 0


@pytest.mark.asyncio
async def test_local_execution_does_not_increment_external_counter():
    item = model()
    sovereignty = FakeSovereignty()
    executor = RoutedInferenceExecutor(ResourceManager(Hardware()), sovereignty, "local")
    await executor.generate(item, FakeProvider(), [Message("user", "hello")])
    assert sovereignty.calls == []


@pytest.mark.asyncio
async def test_multimodal_execution_uses_resources_and_local_sovereignty():
    item = model()
    provider = FakeProvider()
    sovereignty = FakeSovereignty()
    manager = ResourceManager(Hardware())
    executor = RoutedInferenceExecutor(manager, sovereignty, "local")
    result = await executor.generate_with_images(
        item, provider, [Message("user", "image prompt")], [ImageInput("image/png", b"image")]
    )
    assert result.result.text == "image answer"
    assert manager.residency(item.model_id).active_requests == 0
    assert sovereignty.calls == []


@pytest.mark.asyncio
async def test_groq_execution_counts_one_external_inference_and_metadata():
    item = model("groq")
    provider = FakeProvider("groq")
    sovereignty = FakeSovereignty()
    executor = RoutedInferenceExecutor(ResourceManager(Hardware()), sovereignty, "groq")
    execution = await executor.generate(item, provider, [Message("user", "hello")])
    assert len(sovereignty.calls) == 1
    assert sovereignty.calls[0][0] == "groq"
    assert execution.metadata.provider == "groq"
    assert execution.metadata.mode == "groq"
    assert not execution.metadata.local


@pytest.mark.asyncio
async def test_groq_provider_failure_is_not_counted_and_does_not_fallback():
    item = model("groq")
    sovereignty = FakeSovereignty()
    provider = FakeProvider("groq", failure=OSError("failed"))
    executor = RoutedInferenceExecutor(ResourceManager(Hardware()), sovereignty, "groq")
    with pytest.raises(OSError):
        await executor.generate(item, provider, [Message("user", "hello")])
    assert sovereignty.calls == []


@pytest.mark.asyncio
async def test_timeout_cancellation_retains_reservation_until_sync_call_finishes():
    item = model()
    provider = FakeProvider(delay=0.08)
    manager = ResourceManager(Hardware())
    executor = RoutedInferenceExecutor(manager, FakeSovereignty(), "local")
    task = asyncio.create_task(executor.generate(item, provider, [Message("user", "hello")]))
    await asyncio.to_thread(provider.started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert manager.residency(item.model_id).active_requests == 0


@pytest.mark.asyncio
async def test_concurrent_provider_generations_respect_resource_limit():
    item = model()
    manager = ResourceManager(Hardware(), max_concurrency=1)
    provider = FakeProvider(delay=0.03)
    executor = RoutedInferenceExecutor(manager, FakeSovereignty(), "local")
    active = 0
    peak = 0
    original = provider.generate

    def counted(*args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            return original(*args, **kwargs)
        finally:
            active -= 1

    provider.generate = counted
    await asyncio.gather(*[
        executor.generate(item, provider, [Message("user", str(index))]) for index in range(3)
    ])
    assert peak == 1


class NoopTools:
    async def execute(self, decision):
        return {"ok": True, "tool": decision.tool}


class AllowPolicy:
    async def validate(self, ctx, request):
        return PolicyDecision(allowed=True, tool=request.tool, validated_args=request.args, decision_id="id")


class AlwaysVerify:
    async def verify(self, task):
        return True, "ok"


class FakeArtifacts:
    async def create(self, task):
        return []

    async def validate(self, task):
        return True, []


@pytest.mark.asyncio
async def test_real_routed_planner_uses_inference_executor_for_generation():
    item = model(memory=0)
    provider = FakeProvider()
    resources = ResourceManager()
    sovereignty = FakeSovereignty()
    executor = RoutedInferenceExecutor(resources, sovereignty, "local")

    # Exercise direct planner generation too; this is the real routed generation method.
    routed_planner = RoutedPlanner(executor)
    provider.generate = lambda model_id, messages, tools=None: InferenceResult(
        '[{"tool":"read_file","args":{}}]', model_id, "ollama"
    )
    assert await routed_planner._generate(item, provider, [Message("user", "plan")]) == '[{"tool":"read_file","args":{}}]'
    assert resources.residency(item.model_id).active_requests == 0
    assert sovereignty.calls == []


@pytest.mark.asyncio
async def test_orchestrator_routes_planner_generations_through_executor():
    item = model(memory=0)
    responses = iter(["inspection", '[{"tool":"read_file","args":{}}]'])

    class RecordingProvider(FakeProvider):
        def generate(self, model_id, messages, tools=None):
            self.started.set()
            return InferenceResult(next(responses), model_id, self.provider)

    provider = RecordingProvider()
    resources = ResourceManager(max_concurrency=1)
    router = ModelRouter(Settings(), ModelRegistry([item]), {"ollama": provider}, resources)
    sovereignty = FakeSovereignty()
    executor = RoutedInferenceExecutor(resources, sovereignty, "local")
    dependencies = OrchestratorDependencies(
        planner=RoutedPlanner(executor),
        tool_executor=NoopTools(),
        verifier=AlwaysVerify(),
        artifacts=FakeArtifacts(),
        policy=AllowPolicy(),
        tools=(ToolSchema("read_file"),),
        approval=lambda task: asyncio.sleep(0, result=True),
        inference_executor=executor,
    )
    orchestrator = BoundedOrchestrator(router, dependencies)
    ctx = TaskContext(task_id="integration", task_type=None, workspace=__import__("pathlib").Path("."), inference_mode="local")
    events = [event async for event in orchestrator.run(ctx, "inspect this", [])]
    assert events[-1].type == "completed", events[-1].data
    assert len([event for event in events if event.type == "model_selected"]) == 1
    assert resources.residency(item.model_id).active_requests == 0
    assert sovereignty.calls == []


@pytest.mark.asyncio
async def test_audit_failure_does_not_mask_provider_failure():
    item = model()
    audit = FakeAudit()
    audit.fail = True
    provider = FakeProvider(failure=OSError("provider failure"))
    executor = RoutedInferenceExecutor(ResourceManager(Hardware()), FakeSovereignty(), "local", audit)
    with pytest.raises(OSError, match="provider failure"):
        await executor.generate(item, provider, [Message("user", "hello")])
