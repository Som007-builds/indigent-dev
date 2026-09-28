from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.errors import AppError


class SetActiveModelRequest(BaseModel):
    model_id: str = Field(min_length=1)


class RegisterModelRequest(BaseModel):
    id: str
    name: str
    role: str = "reasoning"
    paramCount: str = "70B"
    authorOrOrg: str = "Custom"
    tasks: list[str] = Field(default_factory=list)
    contextLength: int = 32768
    quantization: str = "Q4_K_M"
    speedTokSec: float = 30.0


def router(models_status: Any) -> APIRouter:
    api = APIRouter(prefix="/api")

    @api.get("/models")
    async def models() -> dict:
        try:
            return models_status.status()
        except Exception as exc:
            raise AppError("MODELS_UNAVAILABLE", 503, "Models status is unavailable") from exc

    @api.post("/models/active")
    async def set_active_model(payload: SetActiveModelRequest) -> dict:
        # Fail loudly when the active ModelsStatus cannot record a selection. This
        # previously used `hasattr` and returned {"status": "ok"} either way, so a
        # dropped selection was indistinguishable from a successful one and the
        # switcher appeared to work while never round-tripping (Frontend-fix.md 2.4).
        if not hasattr(models_status, "set_active_model"):
            raise AppError(
                "MODEL_REGISTRY_UNSUPPORTED",
                501,
                "The active models_status implementation does not support model selection",
            )
        try:
            models_status.set_active_model(payload.model_id)
        except Exception as exc:
            raise AppError("MODEL_SWITCH_FAILED", 500, f"Failed to switch model: {exc}") from exc
        return {"status": "ok", "active_model_id": payload.model_id}

    @api.post("/models")
    async def add_model(payload: RegisterModelRequest) -> dict:
        # Same reasoning as above: a discarded registration must not be reported as
        # stored. See Frontend-fix.md item 1.12.
        if not hasattr(models_status, "add_custom_model"):
            raise AppError(
                "MODEL_REGISTRY_UNSUPPORTED",
                501,
                "The active models_status implementation does not support custom model "
                "registration; the model was not stored",
            )
        try:
            model_dict = payload.model_dump()
            model_dict["status"] = "available"
            model_dict["isResident"] = False
            models_status.add_custom_model(model_dict)
        except Exception as exc:
            raise AppError("MODEL_REGISTRATION_FAILED", 500, f"Failed to register model: {exc}") from exc
        return {"status": "ok", "model": model_dict}

    return api
