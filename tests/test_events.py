"""A broken front end must not kill the agent, but cancellation must get through."""

import asyncio

import pytest

from agents_from_scratch.agent import (
    BashCall,
    BashResult,
    Event,
    ToolCancelled,
    ToolEnd,
    ToolStart,
    TurnStart,
    emit,
    run_tool,
)

EVENT = TurnStart(turn=0, max_turns=1)


def test_emit_passes_event_to_callback() -> None:
    events: list[Event] = []

    emit(events.append, EVENT)

    assert events == [EVENT]


def test_emit_swallows_and_logs_callback_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(_: Event) -> None:
        raise ValueError("widget gone")

    emit(broken, EVENT)

    assert "widget gone" in caplog.text


def test_emit_lets_cancellation_through() -> None:
    def cancelled(_: Event) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        emit(cancelled, EVENT)


async def test_run_tool_reports_start_and_end() -> None:
    call = BashCall(id="1", cmd="ls")
    result = BashResult.completed("ls", stdout="a.py", stderr="", returncode=0)
    events: list[Event] = []

    async def tool(_: str) -> BashResult:
        return result

    assert await run_tool(call, tool, events.append) == result
    assert events == [ToolStart(call), ToolEnd(call, result)]


async def test_run_tool_reports_cancellation() -> None:
    """A cancelled command still ends its row, so no bullet stays 'running'."""
    call = BashCall(id="1", cmd="sleep 999")
    started = asyncio.Event()
    events: list[Event] = []

    async def hang(_: str) -> BashResult:
        started.set()
        await asyncio.Event().wait()  # never set
        raise AssertionError("unreachable")

    task = asyncio.create_task(run_tool(call, hang, events.append))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == [ToolStart(call), ToolCancelled(call)]
