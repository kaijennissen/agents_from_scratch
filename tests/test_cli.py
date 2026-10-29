"""Mode selection and argument rules of the command line."""

import pytest

from koding_agent import cli
from koding_agent.cli import Mode, parse_args, select_mode


@pytest.mark.parametrize(
    "argv,mode,tui_prompt,headless_prompt",
    [
        pytest.param([], "tui", None, None, id="no-args-tui"),
        pytest.param(["fix it"], "tui", "fix it", None, id="positional-tui"),
        pytest.param(["-p", "fix it"], "headless", None, "fix it", id="-p"),
        pytest.param(["--prompt", "fix it"], "headless", None, "fix it", id="--prompt"),
        pytest.param(["--plain"], "plain", None, None, id="--plain"),
    ],
)
def test_select_mode(
    argv: list[str], mode: Mode, tui_prompt: str | None, headless_prompt: str | None
) -> None:
    """Each mode reads its prompt from its own argument."""
    args = parse_args(argv)

    assert select_mode(args) == mode
    assert (args.prompt, args.headless_prompt) == (tui_prompt, headless_prompt)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["-p", "x", "--plain"], id="-p+--plain"),
        pytest.param(["first", "-p", "x"], id="positional+-p"),
        pytest.param(["first", "--plain"], id="positional+--plain"),
    ],
)
def test_conflicting_modes_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_tui_without_a_terminal_exits_with_a_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        cli.cli([])
    assert "-p" in str(exc.value.code)
