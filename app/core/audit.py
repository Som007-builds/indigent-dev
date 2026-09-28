import re
from typing import Any

from app.config import Settings

from .repo import Repository

AUDIT_CATEGORIES = frozenset(
    "TASK_CREATED MODEL_SELECTED PROVIDER_CALL RETRIEVAL TOOL_PROPOSED POLICY_ALLOWED POLICY_DENIED TOOL_EXECUTED SANDBOX_STARTED SANDBOX_BLOCKED_NETWORK VERIFICATION_STARTED VERIFICATION_FAILED REPAIR_STARTED ARTIFACT_CREATED ARTIFACT_VALIDATION_FAILED ARTIFACT_VALIDATED APPROVAL_REQUESTED APPROVED TASK_COMPLETED TASK_FAILED FILE_UPLOADED INGEST_STARTED INGEST_FAILED EGRESS_DENIED ARTIFACT_CORRUPT FILE_DOWNLOADED".split()
)
_SENSITIVE_KEY = re.compile(r"key|token|secret|authorization|password", re.IGNORECASE)
_GROQ_KEY = re.compile(r"gsk_[A-Za-z0-9]+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _GROQ_KEY.sub("[REDACTED]", value)
    return value


class AuditLoggerImpl:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    async def emit(
        self,
        category: str,
        component: str,
        action: str,
        status: str = "info",
        task_id: str | None = None,
        details: dict = {},
    ) -> None:
        if category not in AUDIT_CATEGORIES:
            raise ValueError(f"invalid audit category: {category}")
        await self.repo.insert_audit(
            task_id=task_id,
            inference_mode=self.settings.inference_mode,
            category=category,
            component=component,
            action=action,
            status=status,
            details=redact(details),
        )
