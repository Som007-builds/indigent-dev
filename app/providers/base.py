from typing import Protocol

from .types import InferenceResult, Message, ProviderHealth, ToolSchema


class InferenceProvider(Protocol):
    def generate(
        self,
        model_id: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult: ...

    def is_local(self) -> bool: ...

    def health_check(self) -> ProviderHealth: ...
