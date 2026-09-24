from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.models import TaskContext, ToolResult
from app.core.workspace import safe_join
from app.errors import AppError, PathRejectedError
from app.runtime.generators.docx import generate as generate_docx
from app.runtime.generators.xlsx import generate as generate_xlsx
from app.runtime.sandbox import DockerSandbox


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathArgs(_Args):
    path: str


class WriteArgs(PathArgs):
    content: str = Field(max_length=1024 * 1024)


class CodeFile(_Args):
    path: str
    content: str = Field(max_length=1024 * 1024)


class CreateCodeArgs(_Args):
    files: list[CodeFile] = Field(max_length=20)


class ExecuteArgs(_Args):
    entrypoint: str = "main.py"
    args: list[str] = Field(default_factory=list, max_length=10)


class RunTestsArgs(_Args):
    target: str = "tests"


class ArtifactArgs(_Args):
    output: str
    spec: dict


class SearchArgs(_Args):
    query: str = Field(max_length=20_000)
    top_k: int | None = Field(default=None, ge=1, le=100)


class RetrieveArgs(_Args):
    document_id: str
    section: str


class AnalyzeArgs(PathArgs):
    prompt: str | None = Field(default=None, max_length=20_000)


SCHEMAS: dict[str, type[_Args]] = {
    "read_file": PathArgs, "write_file": WriteArgs, "create_code": CreateCodeArgs,
    "execute_code": ExecuteArgs, "run_tests": RunTestsArgs, "create_docx": ArtifactArgs,
    "create_xlsx": ArtifactArgs, "ocr_document": PathArgs, "search_knowledge_base": SearchArgs,
    "retrieve_section": RetrieveArgs, "analyze_image": AnalyzeArgs, "extract_pid_graph": PathArgs,
}


def validate(tool: str, args: dict) -> dict:
    if tool not in SCHEMAS:
        raise AppError("VALIDATION_ERROR", 422, "Unknown tool")
    parsed = SCHEMAS[tool].model_validate(args)
    if tool == "execute_code" and any(len(item) > 200 for item in parsed.args):
        raise AppError("VALIDATION_ERROR", 422, "Command argument is too long")
    return parsed.model_dump(exclude_none=True)


def _workspace_path(ctx: TaskContext, value: str, allowed: set[str]) -> Path:
    path = safe_join(ctx.workspace, value)
    if not path.parts or path.relative_to(ctx.workspace.resolve()).parts[0] not in allowed:
        raise PathRejectedError("Path is outside the permitted workspace directory")
    return path


def validate_paths(ctx: TaskContext, tool: str, args: dict) -> dict:
    checked = dict(args)
    if tool in {"read_file", "ocr_document", "analyze_image", "extract_pid_graph"}:
        checked["path"] = str(_workspace_path(ctx, args["path"], {"inputs", "outputs", "code"}))
    elif tool == "write_file":
        path = _workspace_path(ctx, args["path"], {"code", "outputs"})
        if path.suffix.lower() not in {".py", ".txt", ".md", ".json", ".csv"}:
            raise AppError("VALIDATION_ERROR", 422, "Unsupported output extension")
        checked["path"] = str(path)
    elif tool == "create_code":
        checked["files"] = [
            {**item, "path": str(_workspace_path(ctx, item["path"], {"code"}))}
            for item in args["files"]
        ]
    elif tool == "execute_code":
        checked["entrypoint"] = str(_workspace_path(ctx, args["entrypoint"], {"code"}))
    elif tool == "run_tests":
        checked["target"] = str(_workspace_path(ctx, args["target"], {"code"}))
    elif tool in {"create_docx", "create_xlsx"}:
        checked["output"] = str(_workspace_path(ctx, args["output"], {"outputs"}))
    return checked


class ToolRegistry:
    def __init__(self, sandbox: DockerSandbox, services: Any) -> None:
        self.sandbox, self.services = sandbox, services

    async def run(self, ctx: TaskContext, tool: str, args: dict) -> ToolResult:
        handlers: dict[str, Callable[[TaskContext, dict], Awaitable[ToolResult]]] = {
            "read_file": self.read_file, "write_file": self.write_file, "create_code": self.create_code,
            "execute_code": self.execute_code, "run_tests": self.run_tests, "create_docx": self.create_docx,
            "create_xlsx": self.create_xlsx, "ocr_document": self.ml, "search_knowledge_base": self.ml,
            "retrieve_section": self.ml, "analyze_image": self.ml, "extract_pid_graph": self.ml,
        }
        return await handlers[tool](ctx, {**args, "_tool": tool})

    async def read_file(self, ctx: TaskContext, args: dict) -> ToolResult:
        path = Path(args["path"])
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise AppError("VALIDATION_ERROR", 422, "Text file is missing or too large")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AppError("VALIDATION_ERROR", 422, "File is not text") from exc
        return ToolResult(ok=True, tool="read_file", data={"content": text})

    async def write_file(self, ctx: TaskContext, args: dict) -> ToolResult:
        path = Path(args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        return ToolResult(ok=True, tool="write_file", data={"path": str(path)})

    async def create_code(self, ctx: TaskContext, args: dict) -> ToolResult:
        for item in args["files"]:
            path = Path(item["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item["content"], encoding="utf-8")
        return ToolResult(ok=True, tool="create_code", data={"files": len(args["files"])})

    async def execute_code(self, ctx: TaskContext, args: dict) -> ToolResult:
        entrypoint = Path(args["entrypoint"]).relative_to(safe_join(ctx.workspace, "code"))
        result = await self.sandbox.run(ctx.workspace, ["python", "-B", str(entrypoint), *args.get("args", [])], ctx.task_id)
        return ToolResult(ok=result.exit_code == 0, tool="execute_code", stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code, duration_ms=result.duration_ms, truncated=result.truncated, resource_events=result.resource_events)

    async def run_tests(self, ctx: TaskContext, args: dict) -> ToolResult:
        target = Path(args["target"]).relative_to(safe_join(ctx.workspace, "code"))
        result = await self.sandbox.run(ctx.workspace, ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target)], ctx.task_id)
        data = {"exit_code": result.exit_code, "passed": 0, "failed": 0}
        import re
        match = re.search(r"(\d+) passed", result.stdout + result.stderr)
        if match:
            data["passed"] = int(match.group(1))
        match = re.search(r"(\d+) failed", result.stdout + result.stderr)
        if match:
            data["failed"] = int(match.group(1))
        return ToolResult(ok=result.exit_code == 0, tool="run_tests", data=data, stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code, duration_ms=result.duration_ms, truncated=result.truncated, resource_events=result.resource_events)

    async def create_docx(self, ctx: TaskContext, args: dict) -> ToolResult:
        generate_docx(Path(args["output"]), args["spec"])
        manifest = await self.services.artifacts.register(ctx, "docx", args["output"])
        return ToolResult(ok=True, tool="create_docx", data={"artifact_id": manifest.artifact_id})

    async def create_xlsx(self, ctx: TaskContext, args: dict) -> ToolResult:
        generate_xlsx(Path(args["output"]), args["spec"])
        manifest = await self.services.artifacts.register(ctx, "xlsx", args["output"])
        return ToolResult(ok=True, tool="create_xlsx", data={"artifact_id": manifest.artifact_id})

    async def ml(self, ctx: TaskContext, args: dict) -> ToolResult:
        tool = args.pop("_tool")
        return ToolResult(ok=True, tool=tool, data=await self.services.ml_tools.call(tool, ctx, args))
