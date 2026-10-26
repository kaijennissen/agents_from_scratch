"""Running bash commands, and the observation text the model reads about them."""

import asyncio
import time
from pathlib import Path

import pytest

from agents_from_scratch import agent
from agents_from_scratch.agent import (
    TIMEOUT,
    BashResult,
    format_observation,
    run_bash_tool,
)


@pytest.mark.parametrize(
    "cmd,stdout,stderr,returncode",
    [
        ("echo out; echo err >&2; exit 3", "out\n", "err\n", 3),
        (r"printf '\377'", "\ufffd", "", 0),  # not valid UTF-8
    ],
)
async def test_run_bash_tool_keeps_streams_apart(
    cmd: str, stdout: str, stderr: str, returncode: int
) -> None:
    result = await run_bash_tool(cmd)

    assert result == BashResult.completed(cmd, stdout, stderr, returncode)


async def test_run_bash_tool_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "TIMEOUT", 0.1)
    start = time.monotonic()

    result = await run_bash_tool("sleep 5")

    assert result == BashResult.timeout("sleep 5")
    assert time.monotonic() - start < 1


async def test_run_bash_tool_timeout_kills_child_processes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Killing only the shell would leave its children running unseen."""
    monkeypatch.setattr(agent, "TIMEOUT", 0.1)
    marker = tmp_path / "marker"

    await run_bash_tool(f"(sleep 0.3; touch {marker}) & wait")
    await asyncio.sleep(0.5)

    assert not marker.exists()


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
