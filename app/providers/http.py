import base64
import json
from typing import Any

import httpx

from .types import ImageInput, Message, ToolSchema


def message_payload(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


def image_message_payload(
    messages: list[Message], images: list[ImageInput]
) -> list[dict[str, Any]]:
    payload = message_payload(messages)
    if not payload or payload[-1]["role"] != "user":
        raise ValueError("image input must be attached to a final user message")
    payload[-1]["images"] = [base64.b64encode(image.data).decode("ascii") for image in images]
    return payload


def tool_payload(tools: list[ToolSchema] | None) -> list[dict[str, Any]] | None:
    if tools is None:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def response_text(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        return content, list(message.get("tool_calls") or [])
    message = payload.get("message") or {}
    return str(message.get("content") or payload.get("response") or ""), []


def health(base_url: str, provider: str, timeout: float) -> tuple[bool, str, int | None]:
    try:
        with httpx.Client(base_url=base_url, timeout=timeout) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
        return True, "ready", None
    except (httpx.HTTPError, OSError) as error:
        return False, str(error), None


def json_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":")).encode())
