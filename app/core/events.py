import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from .repo import Repository


class EventBus:
    """Persisted task event stream with race-free replay followed by live delivery."""

    def __init__(self, repo: Repository, inference_mode: str) -> None:
        self.repo = repo
        self.inference_mode = inference_mode
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        seq = await self.repo.insert_event(task_id, event_type, data)
        rows = await self.repo.list_events(task_id, seq - 1)
        row = rows[0]
        event = self._envelope(row)
        async with self._lock:
            for queue in tuple(self._subscribers[task_id]):
                queue.put_nowait(event)
        return event

    async def subscribe(self, task_id: str, after_seq: int = 0) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers[task_id].add(queue)
            replay = await self.repo.list_events(task_id, after_seq)
        last = after_seq
        try:
            for row in replay:
                event = self._envelope(row)
                last = event["id"]
                yield event
            while True:
                event = await queue.get()
                if event["id"] > last:
                    last = event["id"]
                    yield event
        finally:
            async with self._lock:
                self._subscribers[task_id].discard(queue)

    def _envelope(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["seq"],
            "task_id": row["task_id"],
            "ts": row["ts"],
            "type": row["type"],
            "inference_mode": self.inference_mode,
            "data": json.loads(row["data"]),
        }
