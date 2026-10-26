"""A broken front end must not kill the agent, but cancellation must get through."""

import asyncio

import pytest

from agents_from_scratch.agent import Event, TurnStart, emit

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
