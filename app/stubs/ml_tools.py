from app.contracts.models import TaskContext


class StubMlTools:
    async def call(self, tool: str, ctx: TaskContext, args: dict) -> dict:
        return {"tool": tool, "result": "stub", "args": args}
