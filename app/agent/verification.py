"""Task verification derived from recorded tool results.

The orchestrator must not be able to mark its own work verified. This verifier only
reads evidence the runtime actually produced: tool results, exit codes, test counters
and sandbox resource events. A task with no tool results is never verified.
"""

from __future__ import annotations

import json
from typing import Any

RESOURCE_LIMIT_EVENTS = frozenset({"OOM_KILLED", "PIDS_LIMIT"})
TIMEOUT_EVENT = "TIMEOUT"

_TERMINAL_TOOLS = frozenset({"execute_code", "run_tests"})


class TaskVerificationError(ValueError):
    pass


class TaskVerifier:
    """Fail-closed verifier over the task's recorded tool results."""

    def __init__(self, *, require_terminal_result: bool = True) -> None:
        self.require_terminal_result = require_terminal_result

    async def verify(self, task: Any) -> tuple[bool, str]:
        calls = [call for call in (getattr(task, "tool_calls", None) or []) if isinstance(call, dict)]
        if not calls:
            return False, "NO_TOOL_RESULTS"

        for call in calls:
            tool = call.get("tool")
            if call.get("ok") is not True:
                return False, f"TOOL_FAILED:{tool or 'unknown'}:{call.get('error') or 'not ok'}"
            events = {event for event in (call.get("resource_events") or []) if isinstance(event, str)}
            if TIMEOUT_EVENT in events:
                return False, f"TOOL_TIMEOUT:{tool}"
            blocked = events & RESOURCE_LIMIT_EVENTS
            if blocked:
                return False, f"RESOURCE_LIMIT:{tool}:{','.join(sorted(blocked))}"
            exit_code = call.get("exit_code")
            if exit_code not in (0, None):
                return False, f"NONZERO_EXIT:{tool}:{exit_code}"
            data = call.get("data")
            if isinstance(data, dict) and isinstance(data.get("failed"), int) and data["failed"] > 0:
                return False, f"TESTS_FAILED:{tool}:{data['failed']}"

        executed = [call for call in calls if call.get("tool") in _TERMINAL_TOOLS]
        if self.require_terminal_result and not executed:
            return False, "NO_TERMINAL_RESULT"

        summary = {
            "tool_calls": len(calls),
            "tools": sorted({str(call.get("tool")) for call in calls}),
            "terminal_results": len(executed),
        }
        return True, "VERIFIED:" + json.dumps(summary, sort_keys=True)


class AlwaysPassVerifier:
    """Explicit test/demo double; never used by production wiring."""

    async def verify(self, task: Any) -> tuple[bool, str]:
        return True, "unverified-stub"
