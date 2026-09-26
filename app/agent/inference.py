from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Literal, Protocol

from app.contracts.interfaces import Sovereignty
from app.providers import (
    ImageInput,
    InferenceProvider,
    InferenceResult,
    Message,
    ModelInfo,
    ToolSchema,
)

from .resource_manager import ResourceManager


@dataclass(frozen=True)
class InferenceExecutionMetadata:
    mode: Literal["local", "groq"]
    provider: str
    model_id: str
    local: bool
    duration_ms: int
    success: bool


@dataclass(frozen=True)
class InferenceExecution:
    result: InferenceResult
    metadata: InferenceExecutionMetadata


class ProviderCallAudit(Protocol):
    async def emit(
        self,
        category: str,
        component: str,
        action: str,
        status: str = "info",
        task_id: str | None = None,
        details: dict | None = None,
    ) -> None: ...


class RoutedInferenceExecutor:
    """Runs a resolved provider under resource admission and records actual calls."""

    def __init__(
        self,
        resources: ResourceManager,
        sovereignty: Sovereignty,
        inference_mode: str,
        audit: ProviderCallAudit | None = None,
    ) -> None:
        self.resources = resources
        self.sovereignty = sovereignty
        self.inference_mode = inference_mode
        self.audit = audit

    async def generate_with_images(
        self,
        model: ModelInfo,
        provider: InferenceProvider,
        messages: list[Message],
        images: list[ImageInput],
        tools: list[ToolSchema] | None = None,
        *,
        task_id: str | None = None,
    ) -> InferenceExecution:
        method = getattr(provider, "generate_with_images", None)
        if not callable(method):
            raise NotImplementedError("resolved provider does not support multimodal inference")
        if not images:
            raise ValueError("multimodal inference requires at least one image")
        if model.mode != self.inference_mode or provider.is_local() != (self.inference_mode == "local"):
            raise RuntimeError("resolved provider does not match configured inference mode")
        started = monotonic()
        status: Literal["ok", "error"] = "error"
        error: BaseException | None = None
        result: InferenceResult | None = None
        try:
            async with self.resources.acquire(model):
                worker = asyncio.create_task(
                    asyncio.to_thread(method, model.model_id, messages, images, tools)
                )
                try:
                    result = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    try:
                        await asyncio.shield(worker)
                    except Exception:
                        pass
                    raise
            if result.model_id != model.model_id or result.provider != model.provider:
                raise ValueError("provider result metadata does not match the resolved model")
            if model.mode == "groq":
                request_bytes = sum(len(message.content.encode("utf-8")) for message in messages)
                request_bytes += sum(len(image.data) for image in images)
                response_bytes = len(result.text.encode("utf-8"))
                await self.sovereignty.record_external_call(model.provider, request_bytes, response_bytes)
            status = "ok"
        except BaseException as caught:
            error = caught
            raise
        finally:
            if self.audit is not None:
                try:
                    await self.audit.emit(
                        "PROVIDER_CALL", "inference", "generate_with_images", status, task_id,
                        {
                            "inference_mode": self.inference_mode,
                            "provider": model.provider,
                            "model_id": model.model_id,
                            "local": provider.is_local(),
                            "duration_ms": int((monotonic() - started) * 1000),
                            "success": status == "ok",
                            "error_type": type(error).__name__ if error is not None else None,
                        },
                    )
                except Exception:
                    if error is None:
                        raise
        assert result is not None
        return InferenceExecution(
            result=result,
            metadata=InferenceExecutionMetadata(
                mode=model.mode, provider=model.provider, model_id=model.model_id,
                local=provider.is_local(), duration_ms=int((monotonic() - started) * 1000), success=True,
            ),
        )

    async def generate(
        self,
        model: ModelInfo,
        provider: InferenceProvider,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        *,
        task_id: str | None = None,
    ) -> InferenceExecution:
        if model.mode != self.inference_mode or provider.is_local() != (self.inference_mode == "local"):
            raise RuntimeError("resolved provider does not match configured inference mode")
        started = monotonic()
        status: Literal["ok", "error"] = "error"
        error: BaseException | None = None
        result: InferenceResult | None = None
        try:
            async with self.resources.acquire(model):
                worker = asyncio.create_task(
                    asyncio.to_thread(provider.generate, model.model_id, messages, tools)
                )
                try:
                    result = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # Keep the model reservation until synchronous provider I/O ends.
                    try:
                        await asyncio.shield(worker)
                    except Exception:
                        pass
                    raise
            if result.model_id != model.model_id or result.provider != model.provider:
                raise ValueError("provider result metadata does not match the resolved model")
            if model.mode == "groq":
                request_bytes = sum(len(message.content.encode("utf-8")) for message in messages)
                response_bytes = len(result.text.encode("utf-8"))
                await self.sovereignty.record_external_call(model.provider, request_bytes, response_bytes)
            status = "ok"
        except BaseException as caught:
            error = caught
            raise
        finally:
            if self.audit is not None:
                try:
                    await self.audit.emit(
                        "PROVIDER_CALL",
                        "inference",
                        "generate",
                        status,
                        task_id,
                        {
                            "inference_mode": self.inference_mode,
                            "provider": model.provider,
                            "model_id": model.model_id,
                            "local": provider.is_local(),
                            "duration_ms": int((monotonic() - started) * 1000),
                            "success": status == "ok",
                            "error_type": type(error).__name__ if error is not None else None,
                        },
                    )
                except Exception:
                    if error is None:
                        raise
        assert result is not None
        return InferenceExecution(
            result=result,
            metadata=InferenceExecutionMetadata(
                mode=model.mode,
                provider=model.provider,
                model_id=model.model_id,
                local=provider.is_local(),
                duration_ms=int((monotonic() - started) * 1000),
                success=True,
            ),
        )
