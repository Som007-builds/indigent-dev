from typing import Any

from fastapi import APIRouter

from app.errors import AppError


def router(models_status: Any) -> APIRouter:
    api = APIRouter(prefix="/api")

    @api.get("/models")
    async def models() -> dict:
        try:
            return models_status.status()
        except Exception as exc:
            raise AppError("MODELS_UNAVAILABLE", 503, "Models status is unavailable") from exc

    return api
