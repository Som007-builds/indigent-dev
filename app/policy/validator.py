from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.contracts.models import PolicyDecision, TaskContext, ToolRequest
from app.core.workspace import safe_join
from app.errors import PathRejectedError

from .allowlist import ALLOWED_TOOLS, KNOWN_TOOLS
from .schemas import TOOL_POLICIES, ArgumentRule, code_extensions, validate_shape


class PolicyValidatorImpl:
    def __init__(self, *, max_file_size_bytes: int = 50 * 1024 * 1024) -> None:
        self.max_file_size_bytes = max_file_size_bytes

    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision:
        try:
            return self._validate(ctx, req)
        except Exception:
            return self._deny(req.tool if isinstance(req.tool, str) else "", "MALFORMED_TOOL_REQUEST")

    def _validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision:
        if not isinstance(req.tool, str) or not req.tool.strip() or not isinstance(req.args, dict):
            return self._deny(req.tool if isinstance(req.tool, str) else "", "MALFORMED_TOOL_REQUEST")
        if req.tool not in KNOWN_TOOLS or req.tool not in TOOL_POLICIES:
            return self._deny(req.tool, "UNKNOWN_TOOL")
        if ctx.task_type not in ALLOWED_TOOLS:
            return self._deny(req.tool, "UNKNOWN_TASK_TYPE")
        if req.tool not in ALLOWED_TOOLS[ctx.task_type]:
            return self._deny(req.tool, "TOOL_NOT_ALLOWED")
        policy = TOOL_POLICIES[req.tool]
        shape_error = validate_shape(req.args, policy)
        if shape_error is not None:
            return self._deny(req.tool, shape_error)
        if req.tool == "create_code":
            return self._validate_code_files(ctx.workspace, req)
        validated: dict[str, Any] = dict(req.args)
        for name, rule in policy.arguments.items():
            if name not in validated or not rule.path:
                continue
            denial = self._validate_path(ctx.workspace, validated[name], rule)
            if denial is not None:
                return self._deny(req.tool, denial)
            validated[name] = str(safe_join(ctx.workspace, validated[name]))
        return PolicyDecision(
            allowed=True,
            tool=req.tool,
            validated_args=validated,
            decision_id=str(uuid.uuid4()),
        )

    def _validate_code_files(self, workspace: Path, req: ToolRequest) -> PolicyDecision:
        files = req.args["files"]
        if not files:
            return self._deny(req.tool, "INVALID_TOOL_ARGUMENTS: files must not be empty")
        if len(files) > 20:
            return self._deny(req.tool, "RESOURCE_LIMIT: too many code files")
        validated_files: list[dict[str, str]] = []
        for item in files:
            if not isinstance(item, dict):
                return self._deny(req.tool, "INVALID_TOOL_ARGUMENTS: file must be an object")
            if set(item) != {"path", "content"}:
                return self._deny(req.tool, "INVALID_TOOL_ARGUMENTS: each file requires only path and content")
            path_value, content = item["path"], item["content"]
            if not isinstance(path_value, str) or not isinstance(content, str):
                return self._deny(req.tool, "INVALID_TOOL_ARGUMENTS: file path and content must be strings")
            if len(content.encode("utf-8")) > 1024 * 1024:
                return self._deny(req.tool, "RESOURCE_LIMIT: code content exceeds 1 MiB")
            try:
                path = safe_join(workspace, path_value)
                relative = path.relative_to(workspace.resolve())
            except PathRejectedError as error:
                return self._deny(req.tool, f"WORKSPACE_ESCAPE: {error.message}")
            if not relative.parts or relative.parts[0] != "code":
                return self._deny(req.tool, "WORKSPACE_ESCAPE: code path must be inside workspace code")
            if path.suffix.lower() not in code_extensions():
                return self._deny(req.tool, "INVALID_FILE: extension is not permitted")
            validated_files.append({"path": str(path), "content": content})
        return PolicyDecision(
            allowed=True,
            tool=req.tool,
            validated_args={"files": validated_files},
            decision_id=str(uuid.uuid4()),
        )

    def _validate_path(self, workspace: Path, value: str, rule: ArgumentRule) -> str | None:
        try:
            path = safe_join(workspace, value)
        except PathRejectedError as error:
            return f"WORKSPACE_ESCAPE: {error.message}"
        if rule.extensions and path.suffix.lower() not in rule.extensions:
            return "INVALID_FILE: extension is not permitted"
        if rule.must_exist and not path.is_file():
            return "INVALID_FILE: required file does not exist"
        if path.exists() and path.is_file():
            limit = rule.max_size_bytes or self.max_file_size_bytes
            if path.stat().st_size > limit:
                return "INVALID_FILE: file exceeds the permitted size"
        elif rule.max_size_bytes is not None:
            return "INVALID_FILE: file size cannot be established"
        return None

    def _deny(self, tool: str, reason: str) -> PolicyDecision:
        return PolicyDecision(
            allowed=False,
            tool=tool,
            validated_args={},
            decision_id=str(uuid.uuid4()),
            reason=reason,
        )
