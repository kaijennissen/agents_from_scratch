"""The transcript: which events show up, and what they look like."""

from __future__ import annotations

import io

from agents_from_scratch.agent import main
from agents_from_scratch.agent_log import PAD, Verbosity, configure_logging
from conftest import FakeLLM, bash, exit_


def render(verbosity: Verbosity, prompt: str = "what is in src?") -> str:
    out = io.StringIO()
    log = configure_logging(verbosity, stream=out, color=False)
    main(prompt, log=log, call_llm=FakeLLM(bash("seq 1 100"), exit_("done")))
    return out.getvalue()


def test_quiet_keeps_only_the_answer() -> None:
    transcript = render("quiet")
    assert "🎯" in transcript
    assert "👤" not in transcript
    assert "🧠" not in transcript
    assert "⚙️" not in transcript
    assert "📄" not in transcript


def test_normal_shows_every_event_kind() -> None:
    transcript = render("normal")
    for emoji in ("👤", "🧠", "⚙️", "📄", "🎯", "⚡"):
        assert emoji in transcript, emoji


def test_tool_payload_is_truncated_at_normal_and_not_at_verbose() -> None:
    normal = render("normal").splitlines()
    assert any("… 80 more lines" in line for line in normal)
    assert not any(line.strip() == "100" for line in normal)

    verbose = render("verbose").splitlines()
    assert not any("more lines" in line for line in verbose)
    assert any(line.strip() == "100" for line in verbose)


def test_verbose_adds_usage_and_debug_adds_context() -> None:
    assert "1204→88 tok" in render("verbose")
    assert "messages in context" not in render("verbose")
    assert "messages=2" in render("debug")


def test_llm_and_tool_lines_both_carry_the_command() -> None:
    transcript = render("normal")
    assert "🧠 llm    bash · seq 1 100" in transcript
    assert "⚙️ tool   $ seq 1 100" in transcript


def test_payloads_line_up_under_the_label() -> None:
    out = io.StringIO()
    log = configure_logging("normal", stream=out, color=False)
    log.info("tool.result", turn=7, kind="✓", rc=0, out="one\ntwo", err="")
    head, *body = out.getvalue().splitlines()
    assert head.index("📄") == 8  # behind the turn field
    assert body[0].index("one") == len(PAD)
    assert all(line.startswith(PAD) for line in body)


def test_colors_are_opt_in() -> None:
    out = io.StringIO()
    log = configure_logging("normal", stream=out, color=True)
    log.info("agent.final", text="done")
    assert "\x1b[" in out.getvalue()
