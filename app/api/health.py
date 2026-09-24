import asyncio
import ipaddress
from typing import Any
from urllib.parse import urlparse

import docker
import httpx
from fastapi import APIRouter

from app.config import Settings
from app.core.db import Database


def _loopback_url(url: str) -> bool:
    host = urlparse(url).hostname
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def _service_reachable(url: str) -> bool:
    if not _loopback_url(url):
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            response = await client.get(url)
        return response.is_success
    except httpx.HTTPError:
        return False


def _docker_checks(image: str) -> tuple[bool, bool]:
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException:
        return False, False
    try:
        client.images.get(image)
    except docker.errors.ImageNotFound:
        return True, False
    except docker.errors.DockerException:
        return True, False
    return True, True


def router(settings: Settings, database: Database) -> APIRouter:
    api = APIRouter()

    @api.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @api.get("/readyz")
    async def readyz() -> tuple[dict[str, Any], int] | dict[str, Any]:
        try:
            async with database.connection() as connection:
                await connection.execute("SELECT 1")
            sqlite_ok = True
        except Exception:
            sqlite_ok = False
        docker_ok, image_ok = await asyncio.to_thread(_docker_checks, settings.sandbox_image)
        qdrant_ok, ollama_ok = await asyncio.gather(
            _service_reachable(f"{settings.qdrant_url.rstrip('/')}/healthz"),
            _service_reachable(f"{settings.ollama_base_url.rstrip('/')}/api/tags"),
        )
        checks = {
            "sqlite": "ok" if sqlite_ok else "fail",
            "docker": "ok" if docker_ok else "fail",
            "sandbox_image": "ok" if image_ok else "fail",
            "qdrant": "ok" if qdrant_ok else "fail",
            "ollama": "ok" if ollama_ok else "fail",
        }
        # Qdrant and Ollama are informational readiness signals; they do not prevent startup.
        if not (sqlite_ok and docker_ok and image_ok):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=checks)
        return checks

    return api
