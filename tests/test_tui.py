"""Static TUI layout: widgets exist, tools panel collapses, prompt submits."""

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from agents_from_scratch.agent import (
    BashCall,
    BashResult,
    ToolCancelled,
    ToolEnd,
    ToolStart,
    TurnStart,
)
from agents_from_scratch.tui.app import (
    AgentApp,
    PromptArea,
    ToolPanel,
    ToolRow,
    status_for,
)


async def test_layout_has_banner_tools_status_and_input() -> None:
    app = AgentApp(model="some-model")
    async with app.run_test():
        banner = app.query_one("#banner", Static)
        assert "some-model" in str(banner.render())
        assert app.query_one("#conversation", VerticalScroll).children[0] is banner
        assert isinstance(app.query_one("#tools"), ToolPanel)
        assert app.query_one("#status", Static)
        assert app.query_one("#prompt", PromptArea).has_focus


async def test_tab_toggles_tools_panel() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        tools = app.query_one("#tools")
        assert tools.display
        await pilot.press("tab")
        assert not tools.display
        await pilot.press("tab")
        assert tools.display


async def test_submit_echoes_message_and_clears_input() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        await pilot.press(*"hello", "enter")
        messages = app.query(".message.user")
        assert [str(m.render()) for m in messages] == ["> hello"]
        assert app.query_one("#prompt", PromptArea).text == ""


async def test_blank_submit_is_ignored() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        await pilot.press("space", "enter")
        assert len(app.query(".message")) == 0


async def test_ctrl_j_adds_newline_without_submitting() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        await pilot.press("a", "ctrl+j", "b")
        assert app.query_one("#prompt", PromptArea).text == "a\nb"
        assert len(app.query(".message")) == 0


async def test_multiline_message_is_submitted_whole() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        await pilot.press("a", "ctrl+j", "b", "enter")
        assert [str(m.render()) for m in app.query(".message.user")] == ["> a\nb"]
        assert app.query_one("#prompt", PromptArea).text == ""


# --- status_for ---------------------------------------------------------


def test_status_for_zero_exit_is_ok() -> None:
    assert status_for(BashResult.completed("true", "", "", 0)) == "ok"


def test_status_for_nonzero_exit_is_failed() -> None:
    assert status_for(BashResult.completed("false", "", "", 1)) == "failed"


def test_status_for_timeout_is_failed() -> None:
    assert status_for(BashResult.timeout("sleep 9")) == "failed"


# --- ToolRow ------------------------------------------------------------


class RowApp(App[None]):
    def __init__(self, cmd: str) -> None:
        super().__init__()
        self.cmd = cmd

    def compose(self) -> ComposeResult:
        yield ToolRow(BashCall(id="t1", cmd=self.cmd))


def classes_of(row: ToolRow) -> set[str]:
    return {c for c in row.classes if c in {"running", "ok", "failed", "cancelled"}}


async def test_tool_row_starts_running() -> None:
    app = RowApp("ls")
    async with app.run_test():
        row = app.query_one(ToolRow)
        assert row.status == "running"
        assert classes_of(row) == {"running"}


async def test_tool_row_set_status_swaps_the_class() -> None:
    app = RowApp("ls")
    async with app.run_test():
        row = app.query_one(ToolRow)
        for status in ("ok", "failed", "cancelled"):
            row.set_status(status)
            assert row.status == status
            assert classes_of(row) == {status}


async def test_tool_row_shows_command_on_one_line() -> None:
    app = RowApp("echo a\necho b")
    async with app.run_test():
        cmd = app.query_one(".cmd", Static)
        assert str(cmd.render()) == "echo a echo b"


async def test_tool_row_does_not_parse_markup_in_command() -> None:
    app = RowApp("echo [bold]hi[/bold]")
    async with app.run_test():
        cmd = app.query_one(".cmd", Static)
        assert str(cmd.render()) == "echo [bold]hi[/bold]"


# --- forward_event ------------------------------------------------------


def call(id: str, cmd: str = "ls") -> BashCall:
    return BashCall(id=id, cmd=cmd)


def done(cmd: str, returncode: int) -> BashResult:
    return BashResult.completed(cmd, "", "", returncode)


def row_for(app: AgentApp, id: str) -> ToolRow:
    (row,) = [r for r in app.query(ToolRow) if r.call.id == id]
    return row


async def test_tool_start_mounts_a_running_row_in_the_tools_panel() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        app.forward_event(ToolStart(call("a", "ls -la")))
        await pilot.pause()
        (row,) = app.query_one("#tools", ToolPanel).query(ToolRow)
        assert row.status == "running"
        assert str(row.query_one(".cmd", Static).render()) == "ls -la"


async def test_tool_end_zero_exit_marks_row_ok() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        c = call("a")
        app.forward_event(ToolStart(c))
        app.forward_event(ToolEnd(c, done("ls", 0)))
        await pilot.pause()
        assert row_for(app, "a").status == "ok"


async def test_tool_end_nonzero_exit_marks_row_failed() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        c = call("a")
        app.forward_event(ToolStart(c))
        app.forward_event(ToolEnd(c, done("ls", 1)))
        await pilot.pause()
        assert row_for(app, "a").status == "failed"


async def test_tool_end_timeout_marks_row_failed() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        c = call("a", "sleep 9")
        app.forward_event(ToolStart(c))
        app.forward_event(ToolEnd(c, BashResult.timeout("sleep 9")))
        await pilot.pause()
        assert row_for(app, "a").status == "failed"


async def test_tool_cancelled_marks_row_cancelled() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        c = call("a")
        app.forward_event(ToolStart(c))
        app.forward_event(ToolCancelled(c))
        await pilot.pause()
        assert row_for(app, "a").status == "cancelled"


async def test_parallel_tools_are_matched_by_id() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        a, b = call("a", "ls"), call("b", "false")
        app.forward_event(ToolStart(a))
        app.forward_event(ToolStart(b))
        app.forward_event(ToolEnd(b, done("false", 1)))  # B finishes first
        await pilot.pause()
        assert row_for(app, "a").status == "running"
        assert row_for(app, "b").status == "failed"
        app.forward_event(ToolEnd(a, done("ls", 0)))
        await pilot.pause()
        assert row_for(app, "a").status == "ok"


async def test_turn_start_updates_the_status_line() -> None:
    app = AgentApp()
    async with app.run_test() as pilot:
        app.forward_event(TurnStart(0, 5))
        await pilot.pause()
        assert str(app.query_one("#status", Static).render()) == "Working… turn 1/5"


async def test_tool_end_without_start_fails_loudly() -> None:
    app = AgentApp()
    with pytest.raises(KeyError):
        async with app.run_test() as pilot:
            app.forward_event(ToolEnd(call("ghost"), done("ls", 0)))
            await pilot.pause()
