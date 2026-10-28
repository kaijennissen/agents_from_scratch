"""Static TUI layout: widgets exist, tools panel collapses, prompt submits."""

from textual.containers import VerticalScroll
from textual.widgets import Static

from agents_from_scratch.tui.app import AgentApp, PromptArea, ToolPanel


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
