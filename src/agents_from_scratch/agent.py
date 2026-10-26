"""A minimal coding agent: an act -> observe -> decide loop over an LLM.

Each turn: ask the model for one or more actions, execute them (sequentially),
feed the results back. A turn is either one <exit> or one-or-more <bash>
actions; mixing the two is not allowed. The loop ends when the model
emits <exit> or the turn budget runs out.
"""

import argparse
import asyncio
import logging
import os
import re
import signal
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Self, TypedDict, assert_never, cast

import httpx2
from httpx2 import AsyncClient

from agents_from_scratch.banner import (
    GREY,
    RESET,
    print_banner,
    prompt_text,
    rgb,
)

TIMEOUT = 3


RED = rgb("#FF5555")
GREEN = rgb("#50FA7B")
YELLOW = rgb("#FFCC00")


# OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
OLLAMA_ENDPOINT = "http://host.docker.internal:11434/api/chat"
MODEL = "qwen3.8:27b-mlx"

DEFAULT_MAX_TURNS = 25  # safety net; the agent is meant to stop itself with <exit>
MAX_OUTPUT_CHARS = 2000  # tool output is context we pay for on every later turn

SYSTEM_PROMPT = """You are an autonomous coding agent. You solve the user's task by taking one action at a time: you act, observe the result, then decide the next action.
Always explore your environment first. You're running on a computer and have access to a file-system as well as a bash-shell.

Every reply you send is a single <action> element. It contains either exactly one <exit> tag, or one or more <bash> tags. Do not mix <exit> with <bash> in the same action. Output only the <action> element, with nothing before or after it.

The two actions:
- <bash>: run a shell command. Put the command inside the tag. You may issue several <bash> tags in one action; each is executed in turn and every result is sent back to you as the next message, then you continue.
- <exit>: the task is done. This ends the loop. Put your final answer to the user inside the tag. An <exit> action contains no <bash> tags.

Examples:

# Run a command
<action>
<bash>ls -alh /path/to/dir</bash>
</action>

# Run another command
<action>
<bash>wc -l path/to/file.py</bash>
</action>

# Run several independent commands at once (each result comes back together)
<action>
<bash>ls -alh src</bash>
<bash>wc -l src/*.py</bash>
</action>

# Run a command with a pipe
<action>
<bash>grep -rn "ValueError" src | head -n 20</bash>
</action>

# Finish: report a fix
<action>
<exit>Fixed the ValueError in main.py by guarding against the empty list.</exit>
</action>

# Finish: answer a question
<action>
<exit>The project has 12 Python modules, the largest being agent.py at 240 lines.</exit>
</action>

# Finish: nothing to do
<action>
<exit>No changes were needed; the tests already pass.</exit>
</action>
"""


MIXED_ACTIONS_ERROR = (
    "Invalid action: a turn may contain either a single <exit> tag "
    "or one or more <bash> tags, but not both. Re-issue the action "
    "with a single action type."
)


class Message(TypedDict):
    role: str
    content: str


@dataclass(frozen=True)
class BashResult:
    cmd: str
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool

    @classmethod
    def completed(
        cls, cmd: str, stdout: str, stderr: str, returncode: int | None
    ) -> Self:
        return cls(cmd, stdout, stderr, returncode, timed_out=False)

    @classmethod
    def timeout(cls, cmd: str, stdout: str = "", stderr: str = "") -> Self:
        return cls(cmd, stdout, stderr, returncode=None, timed_out=True)


@dataclass(frozen=True, kw_only=True)
class BashCall:
    id: str
    cmd: str


@dataclass(frozen=True, kw_only=True)
class SkillCall:
    id: str
    name: str


type ToolCall = BashCall


@dataclass(frozen=True)
class ToolStart:
    call: ToolCall


@dataclass(frozen=True)
class ToolEnd:
    call: ToolCall
    result: BashResult


@dataclass(frozen=True)
class ToolCancelled:
    call: ToolCall


type Event = ToolStart | ToolEnd | ToolCancelled | TurnStart
type OnEvent = Callable[[Event], None]  # plain def, must return immediately


@dataclass(frozen=True)
class TurnStart:
    turn: int
    max_turns: int


def create_uuid():
    return str(uuid.uuid4()).split("-")[0]


def format_observation(result: BashResult) -> str:
    """Turn a BashResult into the text the model reads."""
    if result.timed_out:
        return (
            f"Command `{result.cmd}` was killed after a timeout of {TIMEOUT} seconds. "
            "It did not finish, so its result and side effects are unknown, "
            "and any output it produced was discarded."
        )
    return (
        f"Command `{result.cmd}` finished with exit code {result.returncode}.\n"
        f'stdout: "{result.stdout}"\n'
        f'stderr: "{result.stderr}"'
    )


async def llm_call(client: AsyncClient, messages: list[Message]) -> str:
    response = await client.post(
        "/api/chat", json={"model": MODEL, "stream": False, "messages": messages}
    )
    response.raise_for_status()
    return cast(str, response.json()["message"]["content"])


def parse_xml(tag: str, string: str) -> list[str]:
    """All contents of <tag>...</tag>, in order of appearance, whitespace-stripped."""
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    return [m.strip() for m in re.findall(pattern, string, re.DOTALL)]


def parse_action(text: str) -> dict[str, list[str]]:
    """Read the model's reply and return the action(s) it asked for.

    A turn is either a single <exit> or one-or-more <bash> actions. Every
    action in the reply must be of the same type; a reply that mixes <exit>
    with <bash> is invalid and is reported as an error. Returns
    {"exit": ["No action"]} when there is no recognised tag at all, so the
    loop always terminates cleanly.
    """
    exit_bodies = parse_xml("exit", text)
    bash_bodies = parse_xml("bash", text)
    if exit_bodies and bash_bodies:
        # Mixing the two action types is not allowed. Signal the mistake as
        # an error so the loop can feed it back and the model can retry,
        # rather than silently terminating.
        return {"error": [MIXED_ACTIONS_ERROR]}
    if exit_bodies:
        return {"exit": exit_bodies}
    if bash_bodies:
        return {"bash": bash_bodies}
    return {"exit": ["No action"]}


def print_event(event: Event) -> None:
    match event:
        case TurnStart(turn=turn, max_turns=max_turns):
            print(f"{GREY}Turn: {turn}/{max_turns}{RESET}")
        case ToolStart(call=BashCall(cmd=cmd)):
            print(f"{YELLOW}running: {cmd}{RESET}")

        case ToolEnd(call=BashCall(cmd=cmd), result=BashResult(returncode=0)):
            print(f"{GREEN}success: {cmd}{RESET}")
        case ToolEnd(call=BashCall(cmd=cmd), result=BashResult(timed_out=True)):
            print(f"{RED}timeout: {cmd}{RESET}")
        case ToolEnd(call=BashCall(cmd=cmd), result=BashResult(returncode=code)):
            print(f"{RED}failure (exit {code}): {cmd}{RESET}")
        case ToolCancelled(call=BashCall(cmd=cmd)):
            print(f"{RED}cancelled: {cmd}{RESET}")
        case _:
            assert_never(event)


async def run_bash_tool(cmd: str):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    proc_id = proc.pid

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        return BashResult.completed(
            cmd=cmd,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            returncode=proc.returncode,
        )

    except TimeoutError:
        return BashResult.timeout(cmd)

    finally:
        try:
            os.killpg(proc_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


def _ignore(_: Event) -> None: ...


def emit(on_event: OnEvent, event: Event) -> None:
    """Call the front end's callback; a broken callback must not kill the agent.

    Catches Exception, not BaseException, so CancelledError still passes through.
    """
    try:
        on_event(event)
    except Exception:
        logging.exception("on_event failed")


async def run_tool(
    tool_call: ToolCall,
    tool_fn: Callable[[str], Awaitable[BashResult]],
    on_event: OnEvent = _ignore,
):
    emit(on_event, ToolStart(call=tool_call))
    try:
        result = await tool_fn(tool_call.cmd)
    except asyncio.CancelledError:
        emit(on_event, ToolCancelled(call=tool_call))
        raise
    emit(on_event, ToolEnd(call=tool_call, result=result))
    return result


async def run_agent(
    messages: list[Message],
    max_turns: int,
    call: Callable[[list[Message]], Awaitable[str]],
    on_event: OnEvent = _ignore,
) -> tuple[str, list[Message]]:
    for turn in range(max_turns):
        emit(on_event, TurnStart(turn, max_turns))

        response = await call(messages)
        # print(response)  # the model speaking: the one moment worth watching
        # not yet appended to messages such that a failure in executing the bash calls doesn't leave the agent in a partial state.
        assistant_msg: Message = {"role": "assistant", "content": response}

        action = parse_action(response)
        if "exit" in action:
            messages += [assistant_msg]
            return action["exit"][0], messages
        if "error" in action:
            # The model mixed action types; tell it why and let it retry.
            messages.extend(
                [assistant_msg, {"role": "user", "content": action["error"][0]}]
            )
            continue

        if "bash" in action:
            # One or more commands, executed in turn; every result is fed
            # back together in a single observation message.
            tool_calls = [BashCall(id=create_uuid(), cmd=cmd) for cmd in action["bash"]]
            results = await asyncio.gather(
                *(
                    run_tool(tool_call, tool_fn=run_bash_tool, on_event=on_event)
                    for tool_call in tool_calls
                )
            )

            observations = [format_observation(result) for result in results]
            messages.extend(
                [
                    assistant_msg,
                    {"role": "user", "content": "\n\n".join(observations)},
                ]
            )

    return f"Ran out of turns ({max_turns}) without an <exit> action.", messages


async def main(prompt: str | None, max_turns: int) -> None:
    async with httpx2.AsyncClient(
        base_url="http://host.docker.internal:11434", timeout=120
    ) as client:
        call = partial(llm_call, client)
        stop: bool = False
        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        if prompt:
            messages.append({"role": "user", "content": prompt})
            answer, _ = await run_agent(
                messages, max_turns=max_turns, call=call, on_event=print_event
            )
            print("\n" + answer + "\n")
        else:
            print_banner(MODEL)  # interactive only; keeps -p output pipe-clean
            while not stop:
                prompt = input(prompt_text())
                if prompt == "exit":
                    stop = True
                else:
                    messages.append({"role": "user", "content": prompt})
                    answer, messages = await run_agent(
                        messages, max_turns=max_turns, call=call, on_event=print_event
                    )
                    print("\n" + answer + "\n")


def cli() -> None:
    parser = argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument("-p", "--prompt", required=False, type=str, help="the prompt")
    parser.add_argument(
        "-t",
        "--max-turns",
        default=DEFAULT_MAX_TURNS,
        type=int,
        help="max turns",
    )
    args = parser.parse_args()

    asyncio.run(main(prompt=args.prompt, max_turns=args.max_turns))


if __name__ == "__main__":
    cli()
