from __future__ import annotations

import httpx
import pytest

from app.agent.registry import ModelRegistry
from app.agent.router import ModelRouter
from app.config import Settings
from app.errors import ModelUnavailableError
from app.providers.groq import GroqProvider
from app.providers.ollama import OllamaProvider
from app.providers.types import ImageInput, Message, ModelInfo


def test_ollama_provider_uses_chat_contract(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": {"content": "ok"}})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    result = OllamaProvider().generate("llama", [Message("user", "hello")])
    assert result.text == "ok"
    assert result.provider == "ollama"


def test_ollama_multimodal_serializes_actual_image_bytes(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": {"content": "graph"}})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    result = OllamaProvider().generate_with_images(
        "local-vlm", [Message("user", "analyze")], [ImageInput("image/png", b"png-bytes")]
    )
    payload = __import__("json").loads(seen["body"])
    assert payload["messages"][-1]["content"] == "analyze"
    assert payload["messages"][-1]["images"] == ["cG5nLWJ5dGVz"]
    assert result.text == "graph"


def test_groq_multimodal_fails_closed():
    with pytest.raises(NotImplementedError, match="not supported"):
        GroqProvider("secret").generate_with_images(
            "model", [Message("user", "analyze")], [ImageInput("image/png", b"png")]
        )


def test_groq_health_requires_explicit_secret():
    health = GroqProvider("").health_check()
    assert not health.available
    assert "not configured" in health.detail


def test_router_never_switches_mode(monkeypatch):
    class HealthyProvider:
        def is_local(self) -> bool:
            return True

        def health_check(self):
            from app.providers.types import ProviderHealth

            return ProviderHealth("ollama", True)

    registry = ModelRegistry(
        [
            ModelInfo(
                "local-model", "local-model", "ollama", "local", frozenset({"inspection"}),
                frozenset({"mac_silicon"}),
            ),
            ModelInfo("remote-model", "remote-model", "groq", "groq", frozenset({"inspection"})),
        ]
    )
    router = ModelRouter(
        Settings(), registry, {"ollama": HealthyProvider()}  # type: ignore[arg-type]
    )
    model, _ = router.resolve("inspection")
    assert model.model_id == "local-model"


def test_router_reports_unavailable_without_fallback():
    settings = Settings(inference_mode="groq")
    registry = ModelRegistry(
        [ModelInfo("remote", "remote", "groq", "groq", frozenset({"coding"}))]
    )
    with pytest.raises(ModelUnavailableError):
        ModelRouter(settings, registry, {}).resolve("inspection")
