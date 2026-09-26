from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.contracts.models import InferenceMode

TaskState = Literal[
    "INTAKE",
    "CLASSIFY",
    "PLAN",
    "RETRIEVE",
    "TOOL",
    "VERIFY",
    "REPAIR",
    "ARTIFACT",
    "ARTIFACT_VALIDATE",
    "APPROVAL",
    "COMPLETE",
    "FAILED",
]


_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    "INTAKE": frozenset({"CLASSIFY", "FAILED"}),
    "CLASSIFY": frozenset({"PLAN", "FAILED"}),
    "PLAN": frozenset({"RETRIEVE", "TOOL", "FAILED"}),
    "RETRIEVE": frozenset({"TOOL", "VERIFY", "FAILED"}),
    "TOOL": frozenset({"VERIFY", "REPAIR", "FAILED"}),
    "VERIFY": frozenset({"REPAIR", "ARTIFACT", "FAILED"}),
    "REPAIR": frozenset({"TOOL", "VERIFY", "ARTIFACT_VALIDATE", "FAILED"}),
    "ARTIFACT": frozenset({"ARTIFACT_VALIDATE", "FAILED"}),
    "ARTIFACT_VALIDATE": frozenset({"APPROVAL", "REPAIR", "FAILED"}),
    "APPROVAL": frozenset({"COMPLETE", "FAILED"}),
    "COMPLETE": frozenset(),
    "FAILED": frozenset(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: TaskState, target: TaskState) -> None:
        super().__init__(f"illegal task transition: {current} -> {target}")
        self.current = current
        self.target = target


@dataclass
class TaskSnapshot:
    task_id: str
    user_request: str
    task_type: str | None
    inference_mode: InferenceMode
    workspace: Path | None = None
    plan: list[str] = field(default_factory=list)
    current_state: TaskState = "INTAKE"
    model_used: str | None = None
    model_provider: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[Any] = field(default_factory=list)
    pid_graph: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    verification_status: str = "pending"
    final_result: Any = None
    requires_human_approval: bool = True
    approved_by: str | None = None
    artifact_validation_result: Any = None

    def transition(self, target: TaskState) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.current_state]:
            raise InvalidTransitionError(self.current_state, target)
        self.current_state = target

    @property
    def terminal(self) -> bool:
        return self.current_state in {"COMPLETE", "FAILED"}
