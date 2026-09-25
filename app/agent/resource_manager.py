from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from app.providers import ModelInfo


@dataclass(frozen=True)
class ResourceSnapshot:
    """Known resource information supplied by an adapter.

    ``None`` means the runtime did not expose that measurement. The manager
    never probes hardware or substitutes a guessed value.
    """

    ram_mb_available: int | None = None
    vram_mb_available: int | None = None


class HardwareResources(Protocol):
    def snapshot(self) -> ResourceSnapshot: ...


@dataclass(frozen=True)
class Residency:
    model_id: str
    loaded: bool
    active_requests: int = 0


@dataclass(frozen=True)
class ResourceRequirements:
    memory_mb: int = 0
    concurrency: int = 1


class ResourceManager:
    """Small, conservative resource and residency tracker.

    The manager tracks reservations made through this process. Actual model
    loading is delegated to optional hooks because Ollama/Groq do not expose a
    portable GPU-memory management API here.
    """

    def __init__(
        self,
        hardware: HardwareResources | None = None,
        max_concurrency: int = 1,
        load_hook: Callable[[ModelInfo], None] | None = None,
        unload_hook: Callable[[ModelInfo], None] | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self.hardware = hardware
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._load_hook = load_hook
        self._unload_hook = unload_hook
        self._residency: dict[str, Residency] = {}
        self._reserved_memory_mb = 0
        self._lock = asyncio.Lock()

    def requirements(self, model: ModelInfo) -> ResourceRequirements:
        memory = max(0, model.memory_estimate_mb)
        return ResourceRequirements(memory_mb=memory)

    def can_select(self, model: ModelInfo) -> bool:
        if not model.available:
            return False
        requirements = self.requirements(model)
        if requirements.memory_mb == 0:
            return True
        if self.hardware is None:
            return False
        snapshot = self.hardware.snapshot()
        available = snapshot.vram_mb_available if model.mode == "local" else snapshot.ram_mb_available
        return available is not None and requirements.memory_mb <= available - self._reserved_memory_mb

    def residency(self, model_id: str) -> Residency:
        return self._residency.get(model_id, Residency(model_id, False))

    def resident_models(self) -> list[str]:
        return [model_id for model_id, state in self._residency.items() if state.loaded]

    async def load(self, model: ModelInfo) -> None:
        async with self._lock:
            if not self.can_select(model):
                raise RuntimeError(f"resources unavailable for model {model.model_id}")
            state = self.residency(model.model_id)
            if state.loaded:
                return
            if self._load_hook is not None:
                self._load_hook(model)
            self._reserved_memory_mb += self.requirements(model).memory_mb
            self._residency[model.model_id] = Residency(model.model_id, True, state.active_requests)

    async def unload(self, model: ModelInfo) -> None:
        async with self._lock:
            state = self.residency(model.model_id)
            if not state.loaded or state.active_requests:
                return
            if self._unload_hook is not None:
                self._unload_hook(model)
            self._reserved_memory_mb = max(
                0, self._reserved_memory_mb - self.requirements(model).memory_mb
            )
            self._residency[model.model_id] = Residency(model.model_id, False)

    @asynccontextmanager
    async def acquire(self, model: ModelInfo) -> AsyncIterator[None]:
        if not self.can_select(model):
            raise RuntimeError(f"resources unavailable for model {model.model_id}")
        await self._semaphore.acquire()
        try:
            if not self.residency(model.model_id).loaded:
                await self.load(model)
            async with self._lock:
                state = self.residency(model.model_id)
                self._residency[model.model_id] = Residency(
                    model.model_id, True, state.active_requests + 1
                )
            yield
        finally:
            async with self._lock:
                state = self.residency(model.model_id)
                self._residency[model.model_id] = Residency(
                    model.model_id, state.loaded, max(0, state.active_requests - 1)
                )
            self._semaphore.release()
