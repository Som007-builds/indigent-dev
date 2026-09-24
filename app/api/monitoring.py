from typing import Any

from fastapi import APIRouter


def router(sovereignty: Any) -> APIRouter:
    api = APIRouter(prefix="/api/monitoring")

    @api.get("/sovereignty")
    async def snapshot() -> dict:
        return await sovereignty.snapshot()

    return api
