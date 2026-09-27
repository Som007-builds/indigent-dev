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
        try:
            if hasattr(models_status, "set_active_model"):
                models_status.set_active_model(payload.model_id)
            return {"status": "ok", "active_model_id": payload.model_id}
        except Exception as exc:
            raise AppError("MODEL_SWITCH_FAILED", 500, f"Failed to switch model: {exc}") from exc

    @api.post("/models")
    async def add_model(payload: RegisterModelRequest) -> dict:
        try:
            model_dict = payload.model_dump()
            model_dict["status"] = "available"
            model_dict["isResident"] = False
            if hasattr(models_status, "add_custom_model"):
                models_status.add_custom_model(model_dict)
            return {"status": "ok", "model": model_dict}
        except Exception as exc:
            raise AppError("MODEL_REGISTRATION_FAILED", 500, f"Failed to register model: {exc}") from exc

    return api
