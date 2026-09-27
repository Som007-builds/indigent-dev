from __future__ import annotations

from typing import Any

from app.config import Settings


class StubModelsStatus:
    """Deterministic substitute for Joy's model registry status.

    The stub reports no real models and no measured resources, and it says so:
    ``hardware_profile`` is ``"stub"`` and the resource budgets are zero. The one
    value it must never invent is the active inference mode, because the frontend
    and the Sovereignty Monitor read this endpoint to decide whether the process is
    air-gapped. It is therefore read from configuration, never hardcoded and never
    defaulted, so ``/api/models`` cannot disagree with the ``X-Inference-Mode``
    header or with ``/api/monitoring/sovereignty``.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        return {
            "active_inference_mode": self.settings.inference_mode,
            "hardware_profile": "stub",
            "models": [],
            "resident_models": [],
            "resources": {
                "vram_mb_free": 0,
                "ram_mb_free": 0,
                "disk_mb_free": 0,
                "max_concurrency": self.settings.resource_max_concurrency,
            },
        }
