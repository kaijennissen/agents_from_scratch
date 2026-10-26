"""The observation text is all the model ever learns about a command."""

import pytest

from agents_from_scratch.agent import TIMEOUT, BashResult, format_observation


@pytest.mark.parametrize(
    "result,present,absent",
    [
        (
            BashResult.completed("pwd", stdout="/repo", stderr="", returncode=0),
            ["pwd", "exit code 0", "stdout", "/repo", "stderr"],
            [],
        ),
        (
            BashResult.completed(
                "ls nope", stdout="", stderr="no such file", returncode=2
            ),
            ["ls nope", "exit code 2", "stdout", "stderr", "no such file"],
            [],
        ),
        (
            BashResult.timeout("sleep 999", stdout="partial", stderr="oops"),
            ["sleep 999", f"{TIMEOUT} seconds"],
            ["exit code", "partial", "oops"],
        ),
    ],
)
def test_format_observation(
    result: BashResult, present: list[str], absent: list[str]
) -> None:
    """Both streams are always labelled; a timeout discards output and exit code."""
    observation = format_observation(result)

    for part in present:
        assert part in observation
    for part in absent:
        assert part not in observation
