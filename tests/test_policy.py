from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.models import TaskContext, ToolRequest
from app.policy.validator import PolicyValidatorImpl


def context(workspace: Path, task_type: str) -> TaskContext:
    workspace.mkdir(parents=True, exist_ok=True)
    return TaskContext(task_id="task", task_type=task_type, workspace=workspace, inference_mode="local")


async def decision(tmp_path, task_type, tool, args):
    return await PolicyValidatorImpl(max_file_size_bytes=4).validate(
        context(tmp_path / "task", task_type), ToolRequest(tool=tool, args=args)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_type", "tool", "args"),
    [
        ("inspection", "search_knowledge_base", {"query": "pump"}),
        ("coding", "write_file", {"path": "code/main.py", "content": "pass"}),
        ("pid_analysis", "extract_pid_graph", {"path": "inputs/pid.png"}),
    ],
)
async def test_allowlisted_tools(tmp_path, task_type, tool, args):
    workspace = tmp_path / "task"
    workspace.mkdir()
    if "path" in args and tool == "extract_pid_graph":
        (workspace / "inputs").mkdir()
        (workspace / "inputs" / "pid.png").write_bytes(b"png")
    result = await PolicyValidatorImpl().validate(context(workspace, task_type), ToolRequest(tool=tool, args=args))
    assert result.allowed


@pytest.mark.asyncio
async def test_unauthorized_and_unknown_tools_fail_closed(tmp_path):
    unauthorized = await decision(tmp_path, "inspection", "write_file", {"path": "x", "content": "x"})
    unknown = await decision(tmp_path, "inspection", "shell", {})
    assert not unauthorized.allowed and unauthorized.reason == "TOOL_NOT_ALLOWED"
    assert not unknown.allowed and unknown.reason == "UNKNOWN_TOOL"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "fragment"),
    [({}, "missing required"), ({"path": 3}, "invalid type"), ({"path": "x", "extra": 1}, "unexpected"),
    ],
)
async def test_argument_validation(tmp_path, args, fragment):
    result = await decision(tmp_path, "inspection", "read_file", args)
    assert not result.allowed and fragment in (result.reason or "")


@pytest.mark.asyncio
async def test_workspace_paths_and_prefix_escape(tmp_path):
    workspace = tmp_path / "task-a"
    workspace.mkdir()
    safe = workspace / "inputs.txt"
    safe.write_text("ok")
    validator = PolicyValidatorImpl()
    allowed = await validator.validate(context(workspace, "inspection"), ToolRequest(tool="read_file", args={"path": "inputs.txt"}))
    traversal = await validator.validate(context(workspace, "inspection"), ToolRequest(tool="read_file", args={"path": "../task-ab/secret.txt"}))
    outside = await validator.validate(context(workspace, "inspection"), ToolRequest(tool="read_file", args={"path": str(tmp_path / "task-ab" / "secret.txt")}))
    assert allowed.allowed and Path(allowed.validated_args["path"]) == safe.resolve()
    assert not traversal.allowed and "WORKSPACE_ESCAPE" in (traversal.reason or "")
    assert not outside.allowed and "WORKSPACE_ESCAPE" in (outside.reason or "")


@pytest.mark.asyncio
async def test_file_extension_and_size(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    (workspace / "bad.exe").write_bytes(b"x")
    (workspace / "large.txt").write_bytes(b"12345")
    validator = PolicyValidatorImpl(max_file_size_bytes=4)
    invalid = await validator.validate(context(workspace, "inspection"), ToolRequest(tool="read_file", args={"path": "bad.exe"}))
    large = await validator.validate(context(workspace, "inspection"), ToolRequest(tool="read_file", args={"path": "large.txt"}))
    assert not invalid.allowed and "INVALID_FILE" in (invalid.reason or "")
    assert not large.allowed and "INVALID_FILE" in (large.reason or "")


@pytest.mark.asyncio
async def test_resource_limit_and_malformed_request(tmp_path):
    limited = await decision(tmp_path, "coding", "execute_code", {"entrypoint": "main.py", "timeout_s": 31})
    assert not limited.allowed and "RESOURCE_LIMIT" in (limited.reason or "")
    with pytest.raises(ValidationError):
        ToolRequest.model_validate({"tool": "read_file", "args": []})


@pytest.mark.asyncio
async def test_policy_does_not_execute(tmp_path):
    path = tmp_path / "task" / "code" / "main.py"
    result = await decision(tmp_path, "coding", "write_file", {"path": "code/main.py", "content": "pass"})
    assert result.allowed and not path.exists()
