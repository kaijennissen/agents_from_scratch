"""A minimal coding agent: an act -> observe -> decide loop over an LLM.

Each turn: ask the model for exactly one action, execute it, feed the result
back. The loop ends when the model emits <exit> or the turn budget runs out.
"""

import argparse
import re
import subprocess
from typing import TypedDict, cast

import httpx2

from agents_from_scratch.banner import print_banner

# OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
OLLAMA_ENDPOINT = "http://host.docker.internal:11434/api/chat"
MODEL = "qwen3.8:27b-mlx"

MAX_TURNS = 15  # safety net; the agent is meant to stop itself with <exit>
MAX_OUTPUT_CHARS = 2000  # tool output is context we pay for on every later turn


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


def llm_call(messages: list[Message]) -> str:
    r = httpx2.post(
        OLLAMA_ENDPOINT,
        json={"model": MODEL, "stream": False, "messages": messages},
        timeout=120,
    )
    r.raise_for_status()
    return cast(str, r.json()["message"]["content"])


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
    return {"exit": "No action"}


def run_agent(messages: list[Message]) -> tuple[str, list[Message]]:
    for _ in range(MAX_TURNS):
        response = llm_call(messages)
        # print(response)  # the model speaking: the one moment worth watching
        messages.append({"role": "assistant", "content": response})

        action = parse_action(response)
        if "exit" in action:
            return action["exit"], messages
        if "bash" in action:
            command = action["bash"]
            result = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            observation = f"Output of `$ {command}`:\n{result.stdout[:MAX_OUTPUT_CHARS]}\n(exit code {result.returncode})"
            messages.append({"role": "user", "content": observation})

    return f"Ran out of turns ({MAX_TURNS}) without an <exit> action.", messages


def main(prompt: str | None) -> None:
    stop: bool = False
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if prompt:
        messages.append({"role": "user", "content": prompt})
        answer, _ = run_agent(messages)
        print(answer)
    else:
        print_banner(MODEL)  # interactive only; keeps -p output pipe-clean
        while not stop:
            prompt = input(">")
            if prompt == "exit":
                stop = True
            else:
                messages.append({"role": "user", "content": prompt})
                answer, messages = run_agent(messages)
                print(answer)


def cli() -> None:
    parser = argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument("-p", "--prompt", required=False, type=str, help="the prompt")
    args = parser.parse_args()

    main(prompt=args.prompt)


if __name__ == "__main__":
    cli()
