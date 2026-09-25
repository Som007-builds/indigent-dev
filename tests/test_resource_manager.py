from __future__ import annotations

import asyncio

import pytest

from app.agent.resource_manager import ResourceManager, ResourceSnapshot
from app.agent.router import ModelRouter
from app.agent.registry import ModelRegistry
from app.config import Settings
from app.errors import ModelUnavailableError
from app.providers.types import ModelInfo, ProviderHealth


class Hardware:
    def __init__(self, snapshot: ResourceSnapshot) -> None:
        self.current = snapshot

    def snapshot(self) -> ResourceSnapshot:
        return self.current


def model(model_id: str = "local") -> ModelInfo:
    return ModelInfo(
        model_id,
        model_id,
        "ollama",
        "local",
        frozenset({"inspection"}),
        frozenset({"mac_silicon"}),
        memory_estimate_mb=100,
    )


def test_unknown_memory_capacity_is_not_fabricated() -> None:
    manager = ResourceManager()
    assert not manager.can_select(model())
    zero_memory = ModelInfo(
        "zero", "zero", "ollama", "local", frozenset({"inspection"}),
        frozenset({"mac_silicon"}), memory_estimate_mb=0,
    )
    assert manager.can_select(zero_memory)


def test_capacity_and_residency_hooks() -> None:
    events: list[str] = []
    manager = ResourceManager(
        Hardware(ResourceSnapshot(vram_mb_available=200)),
        load_hook=lambda item: events.append(f"load:{item.model_id}"),
        unload_hook=lambda item: events.append(f"unload:{item.model_id}"),
    )
    item = model()
    assert manager.can_select(item)
    asyncio.run(manager.load(item))
    assert manager.resident_models() == ["local"]
    asyncio.run(manager.unload(item))
    assert manager.resident_models() == []
    assert events == ["load:local", "unload:local"]


@pytest.mark.asyncio
async def test_concurrency_is_bounded() -> None:
    manager = ResourceManager(Hardware(ResourceSnapshot(vram_mb_available=200)), max_concurrency=1)
    item = model()
    active = 0
    peak = 0

    async def work() -> None:
        nonlocal active, peak
        async with manager.acquire(item):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(work(), work())
    assert peak == 1
    assert manager.residency(item.model_id).active_requests == 0


def test_router_skips_resource_unavailable_models() -> None:
    class Provider:
        def is_local(self) -> bool:
            return True

        def health_check(self) -> ProviderHealth:
            return ProviderHealth("ollama", True)

    manager = ResourceManager(Hardware(ResourceSnapshot(vram_mb_available=50)))
    registry = ModelRegistry([model()])
    router = ModelRouter(  # type: ignore[arg-type]
        Settings(), registry, {"ollama": Provider()}, manager
    )
    with pytest.raises(ModelUnavailableError):
        router.resolve("inspection")
