"""A minimal coding agent: an act -> observe -> decide loop over an LLM.

Each turn: ask the model for exactly one action, execute it, feed the result
back. The loop ends when the model emits <exit> or the turn budget runs out.

Every step is announced on the event stream in agent_log.py — this loop is the
thing being watched, so the transcript is part of the point.
"""

import argparse
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict, cast

import httpx2
import structlog

from agents_from_scratch.agent_log import DEPTHS, configure_logging

# OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
OLLAMA_ENDPOINT = "http://host.docker.internal:11434/api/chat"
MODEL = "qwen3.8:27b-mlx"

MAX_TURNS = 5  # safety net; the agent is meant to stop itself with <exit>
MAX_OUTPUT_CHARS = 2000  # tool output is context we pay for on every later turn
COMMAND_TIMEOUT = 120


class Message(TypedDict):
    role: str
    content: str


SYSTEM_PROMPT = """You are an autonomous coding agent. You solve the user's task by taking one action at a time: you act, observe the result, then decide the next action.
Always explore your environment first. You're running on a computer and have access to a file-system as well as a bash-shell.

Every reply you send is exactly one action, written as a single <action> element containing exactly one of the two inner tags below. Output only the <action> element, with nothing before or after it.

The two actions:
- <bash>: run a shell command. Put the command inside the tag. The command's output is sent back to you as the next message, then you continue.
- <exit>: the task is done. This ends the loop. Put your final answer to the user inside the tag.

Examples:

# Run a command
<action>
<bash>ls -alh /path/to/dir</bash>
</action>

# Run another command
<action>
<bash>wc -l path/to/file.py</bash>
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


@dataclass(frozen=True)
class LLMResponse:
    """One completion, plus the accounting the run summary reports."""

    content: str
    prompt_tokens: int
    tokens: int
    ms: int


def llm_call(messages: list[Message]) -> LLMResponse:
    r = httpx2.post(
        OLLAMA_ENDPOINT,
        json={"model": MODEL, "stream": False, "messages": messages},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return LLMResponse(
        content=cast(str, data["message"]["content"]),
        prompt_tokens=int(data.get("prompt_eval_count", 0)),
        tokens=int(data.get("eval_count", 0)),
        ms=int(data.get("eval_duration", 0)) // 1_000_000,
    )


def parse_xml(tag: str, string: str) -> list[str]:
    """All contents of <tag>...</tag>, in order of appearance, whitespace-stripped."""
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    return [m.strip() for m in re.findall(pattern, string, re.DOTALL)]


def parse_action(text: str) -> dict[str, str]:
    """Read the model's reply and return the single action it asked for.

    The tags are tried in order, so <exit> wins if the reply somehow contains both.
    Returns an empty dict if there is no action tag at all.
    """
    for tag in ("exit", "bash"):
        if bodies := parse_xml(tag, text):
            return {tag: bodies[0]}
    return {}


def main(
    prompt: str,
    *,
    log: structlog.stdlib.BoundLogger | None = None,
    call_llm: Callable[[list[Message]], LLMResponse] = llm_call,
) -> str:
    """Run the loop until the model exits or the turn budget runs out."""
    events = log if log is not None else configure_logging()
    events.info("user.prompt", text=prompt)

    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    tokens = 0
    started = time.monotonic()

    for turn in range(1, MAX_TURNS + 1):
        events = events.bind(turn=turn)
        events.info("llm.request", messages=len(messages))

        response = call_llm(messages)
        tokens += response.prompt_tokens + response.tokens
        events.info(
            "llm.usage",
            text=f"{response.ms / 1000:.1f}s · {response.prompt_tokens}→{response.tokens} tok",
        )
        action = parse_action(response.content)
        if not action:
            events.info("llm.call", kind="unparsed", text=response.content)
            events.info("agent.parse_error", text="no <bash> or <exit> in the reply")
            # Quote the reply back, or the model has no way to see what it got wrong.
            messages.append(
                {
                    "role": "user",
                    "content": "Your reply contained no action. Reply with exactly one "
                    f"<bash> or <exit> action.\n\nYour reply:\n{response.content}",
                }
            )
            continue

        kind, body = next(iter(action.items()))
        events.info("llm.call", kind=kind, text=body)
        messages.append({"role": "assistant", "content": response.content})

        if kind == "exit":
            events.info("agent.final", text=body)
            events.info(
                "run.summary",
                text=f"{turn} turns · {tokens} tok · {time.monotonic() - started:.1f}s",
            )
            return body

        events.info("tool.call", cmd=body)
        called = time.monotonic()
        try:
            result = subprocess.run(
                body,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=COMMAND_TIMEOUT,
            )
            rc, output = result.returncode, result.stdout
        except subprocess.TimeoutExpired:
            rc, output = 124, f"command timed out after {COMMAND_TIMEOUT}s"
        events.info(
            "tool.result",
            kind="✓" if rc == 0 else "✗",
            rc=rc,
            ms=int((time.monotonic() - called) * 1000),
            out=output,
        )
        observation = (
            f"Output of `$ {body}`:\n{output[:MAX_OUTPUT_CHARS]}\n(exit code {rc})"
        )
        messages.append({"role": "user", "content": observation})

    answer = f"Ran out of turns ({MAX_TURNS}) without an <exit> action."
    events.info("agent.final", text=answer)
    events.info(
        "run.summary",
        text=f"{MAX_TURNS} turns · {tokens} tok · {time.monotonic() - started:.1f}s",
    )
    return answer


def cli() -> None:
    parser = argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument("-p", "--prompt", required=True, type=str, help="the prompt")
    parser.add_argument(
        "-v",
        "--verbosity",
        choices=list(DEPTHS),
        default="normal",
        help="quiet: just the answer; verbose: add usage; debug: add context size",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable ANSI colors (also NO_COLOR)"
    )
    args = parser.parse_args()

    main(
        prompt=args.prompt,
        log=configure_logging(args.verbosity, color=False if args.no_color else None),
    )


if __name__ == "__main__":
    cli()
