from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArgumentRule:
    types: tuple[type, ...]
    required: bool = False
    path: bool = False
    extensions: frozenset[str] = frozenset()
    must_exist: bool = False
    max_size_bytes: int | None = None
    max_json_bytes: int | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None


@dataclass(frozen=True)
class ToolPolicy:
    arguments: dict[str, ArgumentRule] = field(default_factory=dict)


_DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".json"}
)
_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})
_CODE_EXTENSIONS = frozenset({".py", ".txt", ".md", ".json", ".csv"})
MAX_SPEC_BYTES = 1024 * 1024

TOOL_POLICIES: dict[str, ToolPolicy] = {
    "read_file": ToolPolicy({"path": ArgumentRule((str,), True, True, _DOCUMENT_EXTENSIONS, True)}),
    "ocr_document": ToolPolicy({"path": ArgumentRule((str,), True, True, _DOCUMENT_EXTENSIONS, True)}),
    "search_knowledge_base": ToolPolicy({"query": ArgumentRule((str,), True)}),
    "retrieve_section": ToolPolicy({"document_id": ArgumentRule((str,), True), "section": ArgumentRule((str,), True)}),
    "create_docx": ToolPolicy(
        {
            "output": ArgumentRule((str,), True, True, frozenset({".docx"})),
            "spec": ArgumentRule((dict,), True, max_json_bytes=MAX_SPEC_BYTES),
        }
    ),
    "create_xlsx": ToolPolicy(
        {
            "output": ArgumentRule((str,), True, True, frozenset({".xlsx"})),
            "spec": ArgumentRule((dict,), True, max_json_bytes=MAX_SPEC_BYTES),
        }
    ),
    "write_file": ToolPolicy({"path": ArgumentRule((str,), True, True), "content": ArgumentRule((str,), True)}),
    "create_code": ToolPolicy({"files": ArgumentRule((list,), True)}),
    "execute_code": ToolPolicy(
        {
            "entrypoint": ArgumentRule((str,), True, True, frozenset({".py"})),
            "timeout_s": ArgumentRule((int, float), False, minimum=0.1, maximum=30),
        }
    ),
    "run_tests": ToolPolicy({"target": ArgumentRule((str,), True, True)}),
    "analyze_image": ToolPolicy({"path": ArgumentRule((str,), True, True, _IMAGE_EXTENSIONS, True)}),
    "extract_pid_graph": ToolPolicy({"path": ArgumentRule((str,), True, True, _IMAGE_EXTENSIONS, True)}),
}


def validate_shape(arguments: Any, policy: ToolPolicy) -> str | None:
    if not isinstance(arguments, dict):
        return "MALFORMED_TOOL_REQUEST: arguments must be an object"
    expected = set(policy.arguments)
    unknown = set(arguments) - expected
    if unknown:
        return "INVALID_TOOL_ARGUMENTS: unexpected arguments: " + ", ".join(sorted(unknown))
    missing = {name for name, rule in policy.arguments.items() if rule.required and name not in arguments}
    if missing:
        return "INVALID_TOOL_ARGUMENTS: missing required arguments: " + ", ".join(sorted(missing))
    for name, value in arguments.items():
        rule = policy.arguments[name]
        if isinstance(value, bool) or not isinstance(value, rule.types):
            return f"INVALID_TOOL_ARGUMENTS: invalid type for {name}"
        if isinstance(value, (int, float)):
            if rule.minimum is not None and value < rule.minimum:
                return f"RESOURCE_LIMIT: {name} is below the permitted minimum"
            if rule.maximum is not None and value > rule.maximum:
                return f"RESOURCE_LIMIT: {name} exceeds the permitted maximum"
        if rule.max_json_bytes is not None:
            try:
                encoded = len(json.dumps(value, default=str).encode())
            except (TypeError, ValueError):
                return f"INVALID_TOOL_ARGUMENTS: {name} is not serializable"
            if encoded > rule.max_json_bytes:
                return f"RESOURCE_LIMIT: {name} exceeds the permitted size"
    return None


def code_extensions() -> frozenset[str]:
    return _CODE_EXTENSIONS
