"""Regression coverage for the APPROVAL/hard-timeout boundary.

AGENTS.md G6 requires ``HARD_TASK_TIMEOUT_S`` to bound *execution* work and to exclude
time a task spends waiting for a human in APPROVAL. The orchestrator therefore
reschedules its execution budget across the approval wait rather than extending it
globally, so these tests pin all three required behaviours:

1. genuine execution overrun still produces ``TASK_TIMEOUT``;
2. an approval wait does not consume the execution budget;
3. a task can be approved after more than a full execution budget has elapsed.

The tests use sub-second budgets so the 300-second production ratio is exercised
structurally instead of by waiting five real minutes.
"""

from __future__ import annotations

import asyncio
from time import monotonic

import pytest
from test_step10_matrix import ToolRuntime, make_orchestrator, run

from app.agent.orchestrator import BoundedOrchestrator


@pytest.mark.asyncio
async def test_execution_overrun_still_times_out():
    """1. Without approval, exceeding the execution budget is still TASK_TIMEOUT."""
    orchestrator = make_orchestrator(
        runtime=ToolRuntime(delay=5.0), approval=lambda task: asyncio.sleep(0, result=True)
    )
    orchestrator.task_timeout_s = 0.15
    started = monotonic()
    events = await run(orchestrator)
    assert monotonic() - started < 2.0, "the budget must fire rather than run to completion"

    assert events[-1].type == "failed"
    assert events[-1].data["error"]["code"] == "TASK_TIMEOUT"


@pytest.mark.asyncio
async def test_approval_wait_exceeding_execution_budget_is_not_a_timeout():
    """2. A wait longer than the whole execution budget must not raise TASK_TIMEOUT."""
    waited = 0.5

    async def slow_approval(task):
        await asyncio.sleep(waited)
        return True

    orchestrator = make_orchestrator(approval=slow_approval)
    orchestrator.task_timeout_s = 0.15
    events = await run(orchestrator)

    assert any(event.type == "approval_requested" for event in events)
    assert events[-1].type == "completed", events[-1].data
    codes = [(event.data.get("error") or {}).get("code") for event in events]
    assert "TASK_TIMEOUT" not in codes


@pytest.mark.asyncio
async def test_approval_completes_after_a_full_execution_budget_elapsed():
    """3. Approval arriving after >1x the execution budget still completes.

    This is the production ratio: HARD_TASK_TIMEOUT_S=300 with a review that takes
    longer than 300s must reach COMPLETE, not TASK_TIMEOUT.
    """
    budget = 0.15
    waited = budget * 3

    async def late_approval(task):
        await asyncio.sleep(waited)
        return True

    orchestrator = make_orchestrator(approval=late_approval)
    orchestrator.task_timeout_s = budget
    orchestrator.approval_timeout_s = 10.0
    events = await run(orchestrator)

    assert events[-1].type == "completed"
    assert any(event.data.get("state") == "APPROVAL" for event in events if event.type == "state_changed")


@pytest.mark.asyncio
async def test_execution_budget_is_still_enforced_after_approval():
    """The post-approval window is a fresh execution budget, not an unbounded one."""
    async def slow_approval(task):
        await asyncio.sleep(0.05)
        return True

    # Approve quickly, then overrun: the fresh post-approval budget must still bite.
    orchestrator = make_orchestrator(approval=slow_approval, runtime=ToolRuntime(delay=5.0))
    orchestrator.task_timeout_s = 0.15
    orchestrator.approval_timeout_s = 10.0
    events = await run(orchestrator)
    assert events[-1].type == "failed"
    assert events[-1].data["error"]["code"] in {"TASK_TIMEOUT", "TOOL_TIMEOUT"}


@pytest.mark.asyncio
async def test_rejection_after_a_long_wait_is_still_rejected():
    """A late rejection must remain a clean REJECTED, not a timeout."""
    async def late_rejection(task):
        await asyncio.sleep(0.5)
        return False

    orchestrator = make_orchestrator(approval=late_rejection)
    orchestrator.task_timeout_s = 0.15
    events = await run(orchestrator)
    assert events[-1].type == "failed"
    assert events[-1].data["error"]["code"] == "REJECTED"


def test_approval_timeout_is_configurable_and_defaults_to_the_contract_value():
    orchestrator = make_orchestrator()
    assert isinstance(orchestrator, BoundedOrchestrator)
    assert orchestrator.approval_timeout_s == 86_400.0
    assert orchestrator.task_timeout_s == 300.0
