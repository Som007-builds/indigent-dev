from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.coding import CodingRepairLoop, GeneratedCode
from app.contracts.models import TaskContext, ToolRequest, ToolResult
from app.policy.validator import PolicyValidatorImpl


def context(workspace: Path) -> TaskContext:
    (workspace / "code" / "tests").mkdir(parents=True, exist_ok=True)
    return TaskContext(task_id="task", task_type="coding", workspace=workspace, inference_mode="local")


async def validate(tmp_path: Path, args: dict):
    return await PolicyValidatorImpl().validate(context(tmp_path / "task"), ToolRequest(tool="create_code", args=args))


@pytest.mark.asyncio
async def test_valid_single_and_multi_file_create_code_contract(tmp_path):
    single = await validate(tmp_path, {"files": [{"path": "code/main.py", "content": "print('ok')"}]})
    multiple = await validate(tmp_path, {"files": [{"path": "code/main.py", "content": "x"}, {"path": "code/tests/test_main.py", "content": "y"}]})
    assert single.allowed
    assert list(single.validated_args) == ["files"]
    assert single.validated_args["files"][0]["content"] == "print('ok')"
    assert Path(single.validated_args["files"][0]["path"]).name == "main.py"
    assert multiple.allowed and len(multiple.validated_args["files"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {},
        {"files": []},
        {"files": ["bad"]},
        {"files": [{"content": "x"}]},
        {"files": [{"path": "code/a.py"}]},
        {"files": [{"path": "code/a.py", "content": "x", "extra": True}]},
        {"files": [{"path": "code/a.py", "content": "x"}], "extra": True},
        {"files": [{"path": "/tmp/a.py", "content": "x"}]},
        {"files": [{"path": "../code/a.py", "content": "x"}]},
        {"files": [{"path": "C:\\code\\a.py", "content": "x"}]},
        {"files": [{"path": "outputs/a.py", "content": "x"}]},
        {"files": [{"path": "code/a.exe", "content": "x"}]},
        {"files": [{"path": 3, "content": "x"}]},
        {"files": [{"path": "code/a.py", "content": 3}]},
    ],
)
async def test_invalid_create_code_shapes_and_paths_fail_closed(tmp_path, args):
    result = await validate(tmp_path, args)
    assert not result.allowed and result.validated_args == {}


@pytest.mark.asyncio
async def test_similar_prefix_escape_and_oversized_content_are_rejected(tmp_path):
    workspace = tmp_path / "task-a"
    ctx = context(workspace)
    validator = PolicyValidatorImpl()
    escape = await validator.validate(ctx, ToolRequest(tool="create_code", args={"files": [{"path": "../task-ab/code/a.py", "content": "x"}]}))
    oversized = await validator.validate(ctx, ToolRequest(tool="create_code", args={"files": [{"path": "code/a.py", "content": "x" * (1024 * 1024 + 1)}]}))
    assert not escape.allowed and "WORKSPACE_ESCAPE" in (escape.reason or "")
    assert not oversized.allowed and "RESOURCE_LIMIT" in (oversized.reason or "")


class Model:
    def generate(self, request, repair_context=None):
        return GeneratedCode("code/main.py", "python", "print('ok')")


class Executor:
    async def execute(self, ctx, decision):
        if decision.tool == "create_code":
            return ToolResult(ok=True, tool=decision.tool, exit_code=0)
        if decision.tool == "execute_code":
            return ToolResult(ok=True, tool=decision.tool, exit_code=0)
        return ToolResult(ok=True, tool=decision.tool, exit_code=0, data={"passed": 1, "failed": 0})


@pytest.mark.asyncio
async def test_coding_repair_loop_request_passes_real_policy(tmp_path):
    ctx = context(tmp_path / "task")
    passed, attempts = await CodingRepairLoop(  # type: ignore[arg-type]
        Model(), PolicyValidatorImpl(), Executor()
    ).run(ctx, "write code", test_target="code/tests")
    assert passed and len(attempts) == 1
