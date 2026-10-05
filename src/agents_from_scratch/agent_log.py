"""How the loop presents itself: one emoji line per event, payload indented.

The loop emits semantic events; this module is the only place that knows what
they look like, so call sites carry no formatting:

    log.info("tool.call", cmd="ls -alh")   -> ⚙️ tool   $ ls -alh
    log.info("agent.final", text=answer)   -> 🎯 done   the answer, wrapped

Payload convention, so the renderer needs no per-event knowledge:

    text      prose, wrapped
    cmd       a shell command, verbatim, `$ `-prefixed
    out/err   verbatim streams, truncated
    other     `key=value` on the head line

Verbosity is a filter over event importance: quiet < normal < verbose < debug.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from collections.abc import Callable, MutableMapping
from typing import Any, Literal, NamedTuple, TextIO, cast

import structlog

Verbosity = Literal["quiet", "normal", "verbose", "debug"]


class Style(NamedTuple):
    emoji: str
    label: str
    color: str
    importance: int = 1  # 0 survives `quiet`; higher needs a deeper verbosity


EVENTS: dict[str, Style] = {
    "user.prompt": Style("👤", "you", "cyan"),
    "llm.call": Style("🧠", "llm", "magenta"),
    "llm.usage": Style("⚡", "llm", "dim", 2),
    "llm.request": Style("🧠", "llm", "dim", 3),
    "tool.call": Style("⚙️", "tool", "yellow"),
    "tool.result": Style("📄", "tool", "green"),
    "agent.final": Style("🎯", "done", "green", 0),
    "agent.parse_error": Style("🧩", "parse", "red", 0),
    "run.summary": Style("⚡", "run", "dim"),
}

DEPTHS: dict[Verbosity, int] = {"quiet": 0, "normal": 1, "verbose": 2, "debug": 3}

#: Every line starts with the same columns — turn field, emoji, label — so
#: payloads of every event line up. Emoji count as the two columns they draw.
PAD = " " * (8 + 2 + 1 + 6 + 1)
MAX_LINES = 20

_COLORS = {
    "bold": 1,
    "dim": 2,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
}


def configure_logging(
    verbosity: Verbosity = "normal",
    stream: TextIO | None = None,
    color: bool | None = None,
) -> structlog.stdlib.BoundLogger:
    """Return a logger that renders events onto `stream` (default stderr)."""
    out = stream if stream is not None else sys.stderr
    depth = DEPTHS[verbosity]
    width = max(min(shutil.get_terminal_size().columns, 400) - len(PAD), 20)
    limit = MAX_LINES if depth < DEPTHS["verbose"] else sys.maxsize
    paint = _painter(_use_color(out) if color is None else color)

    def render(logger: Any, name: str, event: MutableMapping[str, Any]) -> str:
        name = str(event.pop("event"))
        style = EVENTS.get(name, Style("•", name, "", 1))
        if style.importance > depth:
            raise structlog.DropEvent
        text = str(event.pop("text", ""))
        turn = event.pop("turn", 0)
        kind = str(event.pop("kind", ""))
        prose = textwrap.wrap(text, width) if text else []
        command = str(event.pop("cmd", "")).splitlines()
        body = [*prose[1:], *(line[:width] for line in command[1:])]
        for key, prefix in (("out", ""), ("err", "--- stderr ---\n")):
            payload = str(event.pop(key, ""))
            if payload:
                body += [f"{prefix}{line[:width]}" for line in payload.splitlines()]
        if len(body) > limit:
            body = [*body[:limit], f"… {len(body) - limit} more lines"]
        extras = [f"{key}={val}" for key, val in event.items() if val != ""]
        head = " ".join(
            (
                f"turn {turn:>2}" if turn else " " * 7,
                paint(style.emoji, "bold"),
                paint(f"{style.label:<6}", style.color),
            )
        )
        tail = " · ".join(
            part
            for part in [
                kind,
                *prose[:1],
                *(["$ " + command[0][:width]] if command else []),
                *extras,
            ]
            if part
        )
        return "\n".join(
            [f"{head} {tail}" if tail else head, *(f"{PAD}{line}" for line in body)]
        )

    structlog.configure(
        processors=[cast("structlog.types.Processor", render)],
        logger_factory=structlog.PrintLoggerFactory(file=out),
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=False,
    )
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger())


def _painter(color: bool) -> Callable[[str, str], str]:
    if not color:
        return lambda text, _name: text
    return lambda text, name: f"\x1b[{_COLORS.get(name, 0)}m{text}\x1b[0m"


def _use_color(stream: TextIO) -> bool:
    return os.environ.get("NO_COLOR") is None and bool(
        getattr(stream, "isatty", lambda: False)()
    )
