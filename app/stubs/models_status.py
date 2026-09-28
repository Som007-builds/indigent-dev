from __future__ import annotations

import threading
from typing import Any

from app.config import Settings


class StubModelsStatus:
    """Deterministic substitute for Joy's model registry status.

    The stub reports no real models and no measured resources, and it says so:
    ``hardware_profile`` is ``"stub"``, ``models`` is empty and the resource budgets
    are zero. The one value it must never invent is the active inference mode, because
    the frontend and the Sovereignty Monitor read this endpoint to decide whether the
    process is air-gapped. It is therefore read from configuration, never hardcoded and
    never defaulted, so ``/api/models`` cannot disagree with the ``X-Inference-Mode``
    header or with ``/api/monitoring/sovereignty``.

    ``active_model_id`` records the id most recently accepted by
    ``POST /api/models/active`` so that the selection round-trips through
    ``GET /api/models``. It is a record of a *request*, not evidence that a model is
    loaded: because ``models`` is empty, no model is ever resident, and the frontend
    renders "No model loaded" regardless of this value.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._active_model_id: str | None = None
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            active_model_id = self._active_model_id
        return {
            "active_inference_mode": self.settings.inference_mode,
            "hardware_profile": "stub",
            # Always present, `null` until a selection is made. The key is emitted
            # unconditionally so the frontend can distinguish "nothing selected" from
            # "this build does not report a selection" (Frontend-fix.md item 2.4).
            "active_model_id": active_model_id,
            "models": [],
            "resident_models": [],
            "resources": {
                "vram_mb_free": 0,
                "ram_mb_free": 0,
                "disk_mb_free": 0,
                "max_concurrency": self.settings.resource_max_concurrency,
            },
        }

    def set_active_model(self, model_id: str) -> None:
        """Record the requested active model.

        The stub has no registry, so there is nothing to validate the id against and
        nothing to load. Recording the request is the honest behaviour: it makes
        ``GET /api/models`` agree with what ``POST /api/models/active`` acknowledged,
        without claiming any model is resident.
        """
        with self._lock:
            self._active_model_id = model_id
