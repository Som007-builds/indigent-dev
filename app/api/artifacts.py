from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.artifacts import ArtifactStoreImpl, annotate_size
from app.errors import AppError


def router(store: ArtifactStoreImpl) -> APIRouter:
    api = APIRouter(prefix="/api/artifacts")

    @api.get("/{artifact_id}")
    async def get(artifact_id: str, download: bool = False):
        manifest = await store.get(artifact_id)
        if not Path(manifest.path).is_file():
            raise AppError("NOT_FOUND", 404, "Artifact file not found")
        if download:
            await store.require_intact(artifact_id)
            return FileResponse(manifest.path, filename=Path(manifest.path).name)
        response = annotate_size(manifest.model_dump())
        response["download_url"] = f"/api/artifacts/{artifact_id}?download=1"
        return response

    return api
