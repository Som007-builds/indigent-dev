import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.core.db import Database
from app.core.events import EventBus
from app.core.repo import Repository
from app.core.taskrunner import TaskRunner
from app.core.workspace import cleanup_expired
from app.deps import RealControlPlane, build_services
from app.errors import AppError
from app.logging_setup import configure_logging, request_id
from app.net.egress_guard import install as install_egress_guard
from app.net.egress_guard import uninstall as uninstall_egress_guard
from app.stubs.models_status import StubModelsStatus


def create_app(settings: Settings | None = None, models_status: object | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.data_dir, settings.log_level)
    logging.getLogger(__name__).info(
        "startup mode=%s profile=%s", settings.inference_mode, settings.local_hardware_profile
    )
    if settings.inference_mode == "groq":
        logging.getLogger(__name__).warning("EXTERNAL INFERENCE ACTIVE")
    database = Database(settings.data_dir / "db.sqlite")
    repository = Repository(database)
    # Composition reuses this repository so audit, sovereignty, artifacts, the tool
    # runtime and the orchestrator all share one initialized database handle.
    services, orchestrator, rag, pid = build_services(settings, repository=repository)
    audit = services.audit
    if isinstance(orchestrator, RealControlPlane):
        plane = orchestrator
        orchestrator = plane.orchestrator
        models_status = models_status or plane.models_status
    bus = EventBus(repository, settings.inference_mode)
    runner = TaskRunner(repository, bus, services, orchestrator, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.initialize()
        install_egress_guard(settings, repository, audit)
        for task_id in await repository.recover_interrupted_tasks():
            await audit.emit(
                "TASK_FAILED", "startup", "recovered interrupted task", "error", task_id
            )
        async def cleanup_loop() -> None:
            while True:
                await asyncio.to_thread(cleanup_expired, settings)
                await asyncio.sleep(3600)

        cleanup_task = asyncio.create_task(cleanup_loop(), name="workspace-cleanup")
        try:
            yield
        finally:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)
            await runner.shutdown()
            uninstall_egress_guard()

    app = FastAPI(lifespan=lifespan)
    app.state.repository = repository
    app.state.runner = runner
    app.state.artifacts = services.artifacts
    app.state.sovereignty = services.sovereignty
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def headers(request: Request, call_next):
        identifier = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id.set(identifier)
        try:
            content_length = request.headers.get("content-length")
            if (
                request.headers.get("content-type", "").split(";", 1)[0] == "application/json"
                and content_length is not None
                and int(content_length) > 1024 * 1024
            ):
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": "JSON request body exceeds 1 MiB",
                            "request_id": identifier,
                        }
                    },
                )
            else:
                response = await call_next(request)
        finally:
            request_id.reset(token)
        response.headers["X-Request-ID"] = identifier
        response.headers["X-Inference-Mode"] = settings.inference_mode
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.http_status,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "request_id": request_id.get() or request.headers.get("X-Request-ID", ""),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("unhandled request error")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "Internal server error",
                    "request_id": request_id.get() or request.headers.get("X-Request-ID", ""),
                }
            },
        )

    from app.api.artifacts import router as artifacts_router
    from app.api.chat import router as chat_router
    from app.api.files import router as files_router
    from app.api.health import router as health_router
    from app.api.knowledge import router as knowledge_router
    from app.api.models import router as models_router
    from app.api.monitoring import router as monitoring_router
    from app.api.pid import router as pid_router
    from app.api.tasks import router as tasks_router

    app.include_router(chat_router(runner, bus, settings))
    app.include_router(artifacts_router(services.artifacts))
    app.include_router(tasks_router(runner, bus, repository))
    app.include_router(files_router(settings, repository, audit))
    app.include_router(knowledge_router(settings, repository, audit, rag))
    app.include_router(models_router(models_status or getattr(services, "models_status", StubModelsStatus())))
    app.include_router(monitoring_router(services.sovereignty))
    app.include_router(pid_router(settings, repository, audit, pid, services.artifacts))
    app.include_router(health_router(settings, database))

    return app


app = create_app()
