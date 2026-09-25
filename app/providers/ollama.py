from time import monotonic
from typing import Any

import httpx

from .http import health, message_payload, response_text, tool_payload
from .types import InferenceResult, Message, ProviderHealth, ToolSchema


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(
        self,
        model_id: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult:
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": message_payload(messages),
            "stream": False,
        }
        serialized_tools = tool_payload(tools)
        if serialized_tools is not None:
            payload["tools"] = serialized_tools
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            response = client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        text, tool_calls = response_text(body)
        return InferenceResult(text, model_id, "ollama", tool_calls)

    def is_local(self) -> bool:
        return True

    def health_check(self) -> ProviderHealth:
        started = monotonic()
        available, detail, _ = health(self.base_url, "ollama", self.timeout)
        return ProviderHealth(
            "ollama", available, detail, int((monotonic() - started) * 1000)
        )
