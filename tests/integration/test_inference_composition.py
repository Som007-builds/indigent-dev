from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.orchestrator import BoundedOrchestrator, OrchestratorDependencies, RoutedPlanner
from app.agent.resource_manager import ResourceSnapshot
from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext
from app.deps import (
    attach_inference_executor,
    build_inference_control_plane,
    build_services,
)
from app.net.sovereignty import SovereigntyImpl
from app.providers.types import InferenceResult, Message, ProviderHealth


def inventory(mode: str = "local") -> str:
    if mode == "local":
        records = [{
            "model_id": "local-model",
            "provider": "ollama",
            "mode": "local",
            "task_capabilities": ["inspection"],
            "hardware_profiles": ["mac_silicon"],
            "memory_estimate_mb": 1,
            "enabled": True,
        }]
    else:
        records = [{
            "model_id": "groq-model",
            "provider": "groq",
            "mode": "groq",
            "task_capabilities": ["inspection"],
            "hardware_profiles": [],
            "memory_estimate_mb": 1024,
            "enabled": True,
        }]
    return json.dumps(records)


class InMemoryRepository:
    def __init__(self):
        self.counters = {
            "external_api_calls": 0,
            "external_connections": 0,
            "external_bytes_out": 0,
            "external_bytes_in": 0,
            "denied_connections": 0,
            "since": "test",
        }
        self.audit_rows = []

    async def increment_counter(self, name, amount=1):
        self.counters[name] += amount

    async def get_counters(self):
        return dict(self.counters)

    async def insert_audit(self, **row):
        self.audit_rows.append(row)


class InMemoryAudit:
    async def emit(self, category, component, action, status="info", task_id=None, details=None):
        self.rows.append((category, component, action, status, task_id, details))

    def __init__(self):
        self.rows = []


class FakeProvider:
    def __init__(self, name, outputs, *, failure=None):
        self.name = name
        self.outputs = iter(outputs)
        self.failure = failure
        self.calls = []

    def is_local(self):
        return self.name == "ollama"

    def health_check(self):
        return ProviderHealth(self.name, True)

    def generate(self, model_id, messages, tools=None):
        self.calls.append((model_id, messages))
        if self.failure:
            raise self.failure
        return InferenceResult(next(self.outputs), model_id, self.name)


class NullPolicy:
    async def validate(self, ctx, request):
        return PolicyDecision(
            allowed=True, tool=request.tool, validated_args=request.args, decision_id="test"
        )


class Dummy:
    async def execute(self, *args, **kwargs):
        return {"ok": True}

    async def verify(self, task):
        return True, "ok"

    async def create(self, task):
        return []

    async def validate(self, task):
        return True, []


class Planner(RoutedPlanner):
    pass


def dependencies(executor=None):
    return OrchestratorDependencies(
        planner=Planner(executor), tool_executor=Dummy(), verifier=Dummy(),
        artifacts=Dummy(), policy=NullPolicy(), inference_executor=executor,
    )


def test_real_control_plane_uses_configured_router_resources_and_platform_telemetry(monkeypatch):
    settings = Settings(model_inventory_json=inventory(), inference_mode="local")
    repository = InMemoryRepository()
    sovereignty = SovereigntyImpl(repository, settings)
    audit = InMemoryAudit()
    control = build_inference_control_plane(settings, sovereignty, audit)
    control.resources.hardware = type(
        "KnownCapacity", (), {"snapshot": lambda self: ResourceSnapshot(vram_mb_available=2048)}
    )()
    assert control.executor.resources is control.resources
    assert control.router.registry is control.registry
    assert control.router.providers is control.providers
    assert control.executor.sovereignty is sovereignty
    assert control.executor.audit is audit


def test_executor_attaches_to_existing_orchestrator_dependencies():
    settings = Settings(model_inventory_json=inventory())
    control = build_inference_control_plane(settings, SovereigntyImpl(InMemoryRepository(), settings))
    deps = attach_inference_executor(dependencies(), control)
    assert deps.inference_executor is control.executor


@pytest.mark.asyncio
async def test_bounded_orchestrator_consumes_attached_executor():
    settings = Settings(model_inventory_json=inventory())
    repo = InMemoryRepository()
    audit = InMemoryAudit()
    control = build_inference_control_plane(settings, SovereigntyImpl(repo, settings), audit)
    control.resources.hardware = type(
        "KnownCapacity", (), {"snapshot": lambda self: ResourceSnapshot(vram_mb_available=2048)}
    )()
    provider = FakeProvider("ollama", ["inspection", '[{"tool":"read_file","args":{}}]'])
    control.router.providers["ollama"] = provider

    class Approval:
        async def __call__(self, task):
            return True

    deps = attach_inference_executor(dependencies(), control)
    deps = __import__("dataclasses").replace(deps, approval=Approval())
    orchestrator = BoundedOrchestrator(control.router, deps)
    ctx = TaskContext(
        task_id="composition", task_type=None, workspace=Path("."), inference_mode="local"
    )
    events = [event async for event in orchestrator.run(ctx, "inspect", [])]
    assert events[-1].type == "completed", events[-1].data
    assert len(provider.calls) == 2
    assert repo.counters["external_api_calls"] == 0
    assert len(audit.rows) == 2


@pytest.mark.asyncio
async def test_local_classification_and_planning_use_only_local_provider(monkeypatch):
    settings = Settings(model_inventory_json=inventory(), inference_mode="local")
    repo = InMemoryRepository()
    sovereignty = SovereigntyImpl(repo, settings)
    control = build_inference_control_plane(settings, sovereignty, InMemoryAudit())
    local = FakeProvider("ollama", ["inspection", "[]"])
    remote = FakeProvider("groq", ["should-not-run"])
    control.resources.hardware = type(
        "KnownCapacity", (), {"snapshot": lambda self: ResourceSnapshot(vram_mb_available=2048)}
    )()
    control.router.providers.update({"ollama": local, "groq": remote})
    # Generate through the real router/executor boundary for both orchestrator phases.
    model, provider = control.router.resolve("inspection")
    planner = RoutedPlanner(control.executor)
    assert await planner.classify("request", model, provider, task_id="local-task") == "inspection"
    model, provider = control.router.resolve("inspection")
    assert await planner.plan("request", "inspection", (), model, provider, task_id="local-task") == []
    assert len(local.calls) == 2
    assert remote.calls == []
    assert repo.counters["external_api_calls"] == 0
    assert len([row for row in repo.audit_rows if row.get("category") == "PROVIDER_CALL"]) == 0


@pytest.mark.asyncio
async def test_groq_mode_uses_groq_only_and_updates_sovereignty_once_per_generation():
    settings = Settings(inference_mode="groq", groq_api_key="test-only", model_inventory_json=inventory("groq"))
    repo = InMemoryRepository()
    sovereignty = SovereigntyImpl(repo, settings)
    audit = InMemoryAudit()
    control = build_inference_control_plane(settings, sovereignty, audit)
    groq = FakeProvider("groq", ["inspection", "[]"])
    local = FakeProvider("ollama", ["should-not-run"])
    control.resources.hardware = type(
        "KnownRam", (), {"snapshot": lambda self: ResourceSnapshot(ram_mb_available=2048)}
    )()
    control.router.providers.update({"groq": groq, "ollama": local})
    model, provider = control.router.resolve("inspection")
    planner = RoutedPlanner(control.executor)
    await planner.classify("request", model, provider, task_id="groq-task")
    model, provider = control.router.resolve("inspection")
    await planner.plan("request", "inspection", (), model, provider, task_id="groq-task")
    assert len(groq.calls) == 2
    assert local.calls == []
    assert repo.counters["external_api_calls"] == 2
    assert len(audit.rows) == 2
    assert all(row[0] == "PROVIDER_CALL" for row in audit.rows)
    snapshot = await sovereignty.snapshot()
    assert snapshot["status"] == "EXTERNAL INFERENCE ACTIVE"


@pytest.mark.asyncio
async def test_provider_failure_does_not_switch_modes():
    settings = Settings(model_inventory_json=inventory(), inference_mode="local")
    control = build_inference_control_plane(settings, SovereigntyImpl(InMemoryRepository(), settings))
    local = FakeProvider("ollama", [], failure=OSError("local down"))
    groq = FakeProvider("groq", ["fallback"])
    control.resources.hardware = type(
        "KnownCapacity", (), {"snapshot": lambda self: ResourceSnapshot(vram_mb_available=2048)}
    )()
    control.router.providers.update({"ollama": local, "groq": groq})
    model, provider = control.router.resolve("inspection")
    with pytest.raises(OSError, match="local down"):
        await control.executor.generate(model, provider, [Message("user", "prompt")])
    assert len(local.calls) == 1
    assert groq.calls == []


@pytest.mark.asyncio
async def test_resource_failure_does_not_switch_modes():
    settings = Settings(model_inventory_json=inventory(), inference_mode="local")
    control = build_inference_control_plane(settings, SovereigntyImpl(InMemoryRepository(), settings))
    provider = FakeProvider("ollama", ["unused"])
    control.resources.hardware = type(
        "KnownCapacity", (), {"snapshot": lambda self: ResourceSnapshot(vram_mb_available=2048)}
    )()
    control.router.providers["ollama"] = provider
    model, _ = control.router.resolve("inspection")
    # Force admission failure after route resolution to exercise execution gate.
    original_acquire = control.resources.acquire

    class Reject:
        async def __aenter__(self):
            raise RuntimeError("resource unavailable")

        async def __aexit__(self, *args):
            return None

    control.resources.acquire = lambda _: Reject()
    with pytest.raises(RuntimeError, match="resource unavailable"):
        await control.executor.generate(model, provider, [Message("user", "prompt")])
    assert provider.calls == []
    control.resources.acquire = original_acquire


def test_missing_and_malformed_inventory_fail_closed():
    settings = Settings(joy_modules="real")
    with pytest.raises(RuntimeError, match="Invalid real-mode model configuration"):
        build_inference_control_plane(settings, SovereigntyImpl(InMemoryRepository(), settings))
    malformed = Settings(joy_modules="real", model_inventory_json="{")
    with pytest.raises(RuntimeError, match="Invalid real-mode model configuration"):
        build_inference_control_plane(malformed, SovereigntyImpl(InMemoryRepository(), malformed))


def test_real_application_services_still_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match="requires production retrieval configuration"):
        build_services(Settings(data_dir=tmp_path, joy_modules="real"))
