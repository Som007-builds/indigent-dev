import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import Settings
from app.core.events import EventBus
from app.core.taskrunner import TaskRunner


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    file_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)


def router(runner: TaskRunner, bus: EventBus, settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/api")

    @api.post("/chat")
    async def chat(payload: ChatRequest, request: Request):
        if len(payload.message) > settings.max_message_chars:
            from fastapi import HTTPException

            raise HTTPException(422, "message exceeds maximum length")
        task_id = await runner.start(payload.message, payload.file_ids + payload.knowledge_ids)

        async def stream():
            async for event in bus.subscribe(task_id):
                yield {"id": str(event["id"]), "event": event["type"], "data": json.dumps(event)}
                if event["type"] in {"completed", "failed"}:
                    break

        return EventSourceResponse(stream(), ping=15, headers={"X-Task-Id": task_id})

    return api
