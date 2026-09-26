"""Regression coverage for live-memory admission control.

The hardware adapter reports *live* available memory from the OS, so it already
accounts for memory consumed by resident models. These tests pin the corrected
semantics: the OS reading is the only admission signal, and a resident model needs
no new allocation at all.
"""

from __future__ import annotations

import asyncio

from app.agent.resource_manager import ResourceManager, ResourceSnapshot
from app.providers.types import ModelInfo


class Hardware:
    def __init__(self, snapshot: ResourceSnapshot) -> None:
        self.current = snapshot

    def snapshot(self) -> ResourceSnapshot:
        return self.current


def model(model_id: str, memory_mb: int) -> ModelInfo:
    return ModelInfo(
        model_id,
        model_id,
        "ollama",
        "local",
        frozenset({"inspection"}),
        frozenset({"mac_silicon"}),
        memory_estimate_mb=memory_mb,
    )


def test_a_resident_model_is_admitted_without_further_memory() -> None:
    """A: model is loaded and live memory is below its nominal requirement.

    The model already occupies the memory, so requiring a second full allocation
    would make it permanently unselectable.
    """
    hardware = Hardware(ResourceSnapshot(vram_mb_available=4_500))
    manager = ResourceManager(hardware)
    resident = model("resident", 16_030)

    # Precondition: with free memory the model is admissible, so it can be loaded.
    hardware.current = ResourceSnapshot(vram_mb_available=19_000)
    assert manager.can_select(resident)
    asyncio.run(manager.load(resident))
    assert manager.residency("resident").loaded

    # The model is now resident and the OS reports only what is left over.
    hardware.current = ResourceSnapshot(vram_mb_available=4_500)
    assert manager.can_select(resident), "a resident model must not need a second allocation"


def test_b_second_model_is_rejected_when_live_memory_is_insufficient() -> None:
    """B: A resident, B not resident, insufficient live memory for B."""
    hardware = Hardware(ResourceSnapshot(vram_mb_available=20_000))
    manager = ResourceManager(hardware)
    resident = model("a", 16_030)
    other = model("b", 16_030)

    assert manager.can_select(resident)
    asyncio.run(manager.load(resident))

    hardware.current = ResourceSnapshot(vram_mb_available=6_000)
    assert manager.can_select(resident), "the resident model stays admissible"
    assert not manager.can_select(other), "a second 16 GB model must be refused"


def test_c_nonresident_model_with_sufficient_live_memory_is_admitted() -> None:
    """C: ordinary admission against a sufficient live reading."""
    manager = ResourceManager(Hardware(ResourceSnapshot(vram_mb_available=20_000)))
    assert manager.can_select(model("fresh", 16_030))
    assert not manager.can_select(model("too-big", 24_000))


def test_d_missing_hardware_fails_closed_for_a_nonresident_model() -> None:
    """D: no measurement available must refuse rather than assume capacity."""
    manager = ResourceManager()
    assert not manager.can_select(model("unknown", 16_030))
    zero = model("zero", 0)
    assert manager.can_select(zero), "a zero-memory model needs no measurement"


def test_e_stale_reservation_does_not_block_selection() -> None:
    """E: provider-side idle eviction frees memory; stale bookkeeping must not reject.

    Ollama evicts an idle model on its own and nothing reports that back, so
    ``_reserved_memory_mb`` can stay nonzero while the OS memory is genuinely free.
    Selection must follow the OS, not the stale counter.
    """
    manager = ResourceManager(Hardware(ResourceSnapshot(vram_mb_available=20_000)))
    item = model("evicted", 16_030)
    asyncio.run(manager.load(item))
    assert manager._reserved_memory_mb == 16_030
    assert manager.residency("evicted").loaded

    # Simulate the provider dropping the model: memory returns, bookkeeping does not.
    hardware_free = ResourceSnapshot(vram_mb_available=20_000)
    manager.hardware.current = hardware_free
    assert manager._reserved_memory_mb > 0, "reservation is deliberately left stale"
    assert manager.can_select(item), "stale reservation must not veto a live-sufficient model"


def test_live_reading_is_not_reduced_by_the_reservation_counter() -> None:
    """The OS reading is authoritative: it must never be reduced by the counter."""
    hardware = Hardware(ResourceSnapshot(vram_mb_available=20_000))
    manager = ResourceManager(hardware)
    big = model("big", 16_030)
    asyncio.run(manager.load(big))
    assert manager._reserved_memory_mb > 0

    # 20 GB free and a 16 GB nonresident requirement: admissible, because the live
    # reading alone decides. A reduced reading (20 - 16 = 4) would wrongly refuse this.
    other = model("other", 16_030)
    assert manager.can_select(other), "reservation must not be subtracted from live memory"


def test_unavailable_model_is_never_admitted() -> None:
    manager = ResourceManager(Hardware(ResourceSnapshot(vram_mb_available=64_000)))
    unavailable = ModelInfo(
        "down", "down", "ollama", "local", frozenset({"inspection"}),
        frozenset({"mac_silicon"}), memory_estimate_mb=16_030, available=False,
    )
    assert not manager.can_select(unavailable)
