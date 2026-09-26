from __future__ import annotations

import json

import pytest

from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager, ResourceSnapshot
from app.agent.router import ModelRouter
from app.config import ModelInventoryRecord, Settings
from app.deps import build_model_routing
from app.errors import ModelUnavailableError
from app.providers.types import ProviderHealth


def record(
    model_id="local-inspection",
    provider="ollama",
    mode="local",
    tasks=("inspection",),
    profiles=("mac_silicon",),
    memory=1024,
    enabled=True,
):
    return {
        "model_id": model_id,
        "provider": provider,
        "mode": mode,
        "task_capabilities": list(tasks),
        "hardware_profiles": list(profiles),
        "memory_estimate_mb": memory,
        "enabled": enabled,
    }


class Provider:
    def __init__(self, local: bool, available: bool = True):
        self.local = local
        self.available = available

    def is_local(self):
        return self.local

    def health_check(self):
        return ProviderHealth("ollama" if self.local else "groq", self.available)

    def generate(self, model_id, messages, tools=None):
        raise AssertionError("routing test should not generate")


class Hardware:
    def __init__(self, vram: int | None, ram: int | None = None):
        self.value = ResourceSnapshot(vram_mb_available=vram, ram_mb_available=ram)

    def snapshot(self):
        return self.value


def settings_with(items, **kwargs):
    return Settings(model_inventory_json=json.dumps(items), **kwargs)


def test_valid_inventory_loads_to_existing_model_info():
    settings = settings_with([record()])
    configured = settings.model_inventory()
    assert len(configured) == 1
    assert configured[0].to_model_info().memory_estimate_mb == 1024


@pytest.mark.parametrize(
    "items",
    [
        [record(), record()],
        [{**record(), "provider": "other"}],
        [{**record(), "mode": "remote"}],
        [{**record(), "task_capabilities": ["unknown"]}],
        [{**record(), "hardware_profiles": ["unknown"]}],
        [{**record(), "memory_estimate_mb": 0}],
        [{**record(), "provider": "groq"}],
        [{**record(), "mode": "groq", "provider": "groq", "hardware_profiles": ["mac_silicon"]}],
    ],
)
def test_invalid_inventory_rejected(items):
    with pytest.raises(ValueError):
        settings_with(items).model_inventory()


def test_missing_and_malformed_inventory_fail_loudly():
    with pytest.raises(ValueError, match="required"):
        Settings().model_inventory()
    with pytest.raises(ValueError, match="valid JSON"):
        Settings(model_inventory_json="{").model_inventory()
    with pytest.raises(ValueError, match="non-empty"):
        Settings(model_inventory_json="[]").model_inventory()


def test_disabled_model_is_retained_but_never_routed():
    disabled = record(enabled=False)
    model = ModelInventoryRecord.model_validate(disabled).to_model_info()
    registry = ModelRegistry([model])
    router = ModelRouter(Settings(), registry, {"ollama": Provider(True)})
    assert registry.get(model.model_id) is not None
    with pytest.raises(ModelUnavailableError):
        router.resolve("inspection")


def test_router_selects_only_active_mode_and_no_cross_mode_fallback():
    local = ModelInventoryRecord.model_validate(record()).to_model_info()
    groq = ModelInventoryRecord.model_validate(
        record("groq-dev", "groq", "groq", profiles=())
    ).to_model_info()
    providers = {"ollama": Provider(True), "groq": Provider(False)}
    registry = ModelRegistry([local, groq])

    selected, _ = ModelRouter(Settings(inference_mode="local"), registry, providers).resolve("inspection")
    assert selected.mode == "local"
    selected, _ = ModelRouter(Settings(inference_mode="groq"), registry, providers).resolve("inspection")
    assert selected.mode == "groq"

    unavailable_local = ModelRouter(
        Settings(inference_mode="local"), registry,
        {"ollama": Provider(True, False), "groq": Provider(False)},
    )
    with pytest.raises(ModelUnavailableError):
        unavailable_local.resolve("inspection")
    unavailable_groq = ModelRouter(
        Settings(inference_mode="groq"), registry,
        {"ollama": Provider(True), "groq": Provider(False, False)},
    )
    with pytest.raises(ModelUnavailableError):
        unavailable_groq.resolve("inspection")


def test_resource_manager_capacity_rejects_configured_model():
    model = ModelInventoryRecord.model_validate(record()).to_model_info()
    router = ModelRouter(
        Settings(), ModelRegistry([model]), {"ollama": Provider(True)},
        ResourceManager(Hardware(vram=512)),
    )
    with pytest.raises(ModelUnavailableError):
        router.resolve("inspection")


def test_real_model_routing_construction_uses_explicit_inventory():
    configured = settings_with([record() ], joy_modules="real")
    registry, router, resources, providers = build_model_routing(configured)
    assert registry.models()[0].model_id == "local-inspection"
    assert router.settings.inference_mode == "local"
    assert resources.max_concurrency == configured.resource_max_concurrency
    assert set(providers) == {"ollama", "groq"}



def test_real_model_routing_construction_rejects_missing_inventory():
    with pytest.raises(RuntimeError, match="Invalid real-mode model configuration"):
        build_model_routing(Settings(joy_modules="real"))
