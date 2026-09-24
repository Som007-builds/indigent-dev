import asyncio

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.api import health
from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_readyz_reports_every_check_and_docker_failure_is_503(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "_docker_checks", lambda _: (False, False))
    monkeypatch.setattr(health, "_service_reachable", lambda _: asyncio.sleep(0, result=False))
    app = create_app(Settings(data_dir=tmp_path))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "sqlite": "ok",
        "docker": "fail",
        "sandbox_image": "fail",
        "qdrant": "fail",
        "ollama": "fail",
    }


@pytest.mark.asyncio
async def test_unhandled_error_is_clean_and_json_body_limit_is_enforced(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    test_router = APIRouter()

    @test_router.get("/explode")
    async def explode() -> None:
        raise RuntimeError("traceback should stay private")

    @test_router.post("/json")
    async def json_endpoint() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(test_router)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            error = await client.get("/explode")
            oversized = await client.post("/json", content=b"x" * (1024 * 1024 + 1), headers={"content-type": "application/json"})
    assert error.status_code == 500
    assert error.json()["error"]["code"] == "INTERNAL"
    assert "traceback" not in error.text
    assert oversized.status_code == 413
