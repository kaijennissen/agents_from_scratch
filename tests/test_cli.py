"""Mode selection and argument rules of the command line."""

import pytest

from agents_from_scratch import cli
from agents_from_scratch.cli import parse_args, select_mode


def mode(*argv: str) -> str:
    return select_mode(parse_args(list(argv)))


def test_no_arguments_opens_the_tui() -> None:
    assert mode() == "tui"


def test_positional_prompt_opens_the_tui_with_it() -> None:
    args = parse_args(["fix the bug"])
    assert select_mode(args) == "tui"
    assert args.prompt == "fix the bug"


def test_dash_p_is_headless() -> None:
    args = parse_args(["-p", "fix the bug"])
    assert select_mode(args) == "headless"
    assert args.headless_prompt == "fix the bug"


def test_long_prompt_flag_is_still_accepted() -> None:
    assert mode("--prompt", "x") == "headless"


def test_plain_flag_selects_the_repl() -> None:
    assert mode("--plain") == "plain"


@pytest.mark.parametrize(
    "argv", [["-p", "x", "--plain"], ["first", "-p", "x"], ["first", "--plain"]]
)
def test_conflicting_modes_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_max_turns_is_parsed() -> None:
    assert parse_args(["-t", "3"]).max_turns == 3


def test_tui_without_a_terminal_exits_with_a_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        cli.cli([])
    assert "-p" in str(exc.value.code)
