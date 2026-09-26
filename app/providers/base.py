from typing import Protocol

from .types import ImageInput, InferenceResult, Message, ProviderHealth, ToolSchema


class InferenceProvider(Protocol):
    def generate(
        self,
        model_id: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult: ...

    def generate_with_images(
        self,
        model_id: str,
        messages: list[Message],
        images: list[ImageInput],
        tools: list[ToolSchema] | None = None,
    ) -> InferenceResult: ...

    def is_local(self) -> bool: ...

    def supports_images(self) -> bool:
        """Whether this adapter can carry image input at all.

        This is an adapter-level capability, not a guarantee that a specific model is a
        vision model; it exists so image-only task types are never routed to a provider
        that would silently drop the image.
        """
        ...

    def health_check(self) -> ProviderHealth: ...
