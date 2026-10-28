"""Static layout of the TUI: banner, conversation, tools panel, status, prompt.

No agent is wired in yet; submitting a message only echoes it into the
conversation.
"""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Static, TextArea

from agents_from_scratch.banner import render_banner

DEFAULT_MODEL = "unknown-model"


class ToolPanel(VerticalScroll):
    """Right-hand column listing tool calls. Empty until tools are wired in."""

    def on_mount(self) -> None:
        self.border_title = "Tools"


class PromptArea(TextArea):
    """Multi-line prompt: Enter submits, Ctrl+J (or Shift+Enter) adds a newline.

    Shift+Enter only reaches us in terminals with an enhanced keyboard
    protocol; elsewhere it looks like Enter, so Ctrl+J is the dependable key.
    """

    BINDINGS = [
        Binding("enter", "submit", "Send", priority=True),
        Binding("ctrl+j,shift+enter", "newline", "Newline", priority=True),
    ]

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def action_submit(self) -> None:
        self.post_message(self.Submitted(self.text))

    def action_newline(self) -> None:
        self.insert("\n")


class AgentApp(App[None]):
    CSS = """
    #main { height: 1fr; }
    #conversation { width: 1fr; border: round $primary; padding: 0 1; }
    #tools { width: 32; border: round $secondary; padding: 0 1; }
    #tools.collapsed { display: none; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    #prompt { height: auto; min-height: 3; max-height: 10; }
    .message { margin: 1 0 0 0; }
    .message.user { background: $boost; padding: 0 1; }
    """

    BINDINGS = [
        Binding("tab", "toggle_tools", "Tools", priority=True),
        Binding("ctrl+c", "quit", "Exit", priority=True),
    ]

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        super().__init__()
        self.model = model

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            conversation = VerticalScroll(id="conversation")
            conversation.border_title = "Conversation"
            with conversation:
                yield Static(
                    Text.from_ansi(render_banner(self.model, color=True)), id="banner"
                )
            yield ToolPanel(id="tools")
        yield Static("", id="status")
        prompt = PromptArea(placeholder="Send a message", id="prompt", soft_wrap=True)
        prompt.border_title = "Message"
        yield prompt
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#prompt", PromptArea).focus()

    def action_toggle_tools(self) -> None:
        self.query_one("#tools").toggle_class("collapsed")

    async def on_prompt_area_submitted(self, event: PromptArea.Submitted) -> None:
        text = event.text.strip()
        self.query_one("#prompt", PromptArea).clear()
        if not text:
            return
        conversation = self.query_one("#conversation", VerticalScroll)
        await conversation.mount(Static(f"> {text}", classes="message user"))
        conversation.scroll_end(animate=False)


def run() -> None:
    AgentApp().run()


if __name__ == "__main__":
    run()
