from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


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
    provider: str
    mode: Literal["local", "groq"]
    task_types: frozenset[str]
    hardware_profiles: frozenset[str] = frozenset()
    memory_estimate_mb: int = 0
    available: bool = True
