from time import monotonic
from typing import Any

import httpx

from .http import message_payload, response_text, tool_payload
from .types import ImageInput, InferenceResult, Message, ProviderHealth, ToolSchema


class GroqProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(
        self,
        model_id: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult:
        payload: dict[str, Any] = {"model": model_id, "messages": message_payload(messages)}
        serialized_tools = tool_payload(tools)
        if serialized_tools is not None:
            payload["tools"] = serialized_tools
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=headers) as client:
            response = client.post("/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        text, tool_calls = response_text(body)
        usage = body.get("usage") or {}
        return InferenceResult(
            text,
            model_id,
            "groq",
            tool_calls,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

    def generate_with_images(
        self,
        model_id: str,
        messages: list[Message],
        images: list[ImageInput],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult:
        raise NotImplementedError("Groq multimodal inference is not supported by this adapter")

    def is_local(self) -> bool:
        return False

    def supports_images(self) -> bool:
        return False

    def health_check(self) -> ProviderHealth:
        started = monotonic()
        if not self.api_key:
            return ProviderHealth("groq", False, "GROQ_API_KEY is not configured", 0)
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as client:
                response = client.get("/models")
                response.raise_for_status()
            return ProviderHealth("groq", True, "ready", int((monotonic() - started) * 1000))
        except (httpx.HTTPError, OSError) as error:
            return ProviderHealth(
                "groq", False, str(error), int((monotonic() - started) * 1000)
            )
