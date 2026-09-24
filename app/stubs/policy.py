import uuid

from app.contracts.models import PolicyDecision, TaskContext, ToolRequest

ALLOWED_TOOLS = {
    "inspection": {
        "read_file",
        "ocr_document",
        "search_knowledge_base",
        "retrieve_section",
        "create_docx",
        "create_xlsx",
    },
    "coding": {"read_file", "write_file", "create_code", "execute_code", "run_tests"},
    "pid_analysis": {"analyze_image", "extract_pid_graph"},
}


class StubPolicy:
    async def validate(self, ctx: TaskContext, req: ToolRequest) -> PolicyDecision:
        allowed = req.tool in ALLOWED_TOOLS.get(ctx.task_type or "", set())
        return PolicyDecision(
            allowed=allowed,
            tool=req.tool,
            validated_args=req.args,
            decision_id=str(uuid.uuid4()),
            reason=None if allowed else "Tool is not allow-listed",
        )
