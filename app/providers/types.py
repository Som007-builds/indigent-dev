from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass(frozen=True)
class ImageInput:
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data: bytes

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("image input must not be empty")



@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResult:
    text: str
    model_id: str
    provider: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    available: bool
    detail: str = ""
    latency_ms: int | None = None


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    model_name: str
    provider: Literal["ollama", "groq"]
    mode: Literal["local", "groq"]
    task_types: frozenset[Literal["inspection", "coding", "pid_analysis"]]
    hardware_profiles: frozenset[Literal["mac_silicon", "rtx_3050a_4gb"]] = frozenset()
    memory_estimate_mb: int = 0
    available: bool = True
    modalities: frozenset[Literal["text", "image"]] = frozenset(["text"])
