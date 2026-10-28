"""Command line entry point: picks a mode and wires the core to a front end.

    agents-from-scratch [PROMPT]       TUI; PROMPT, if given, is sent first
    agents-from-scratch -p PROMPT      headless one-shot, pipe-clean output
    agents-from-scratch --plain        line-based REPL

This is the only module that imports both the core and the front ends.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from functools import partial
from typing import Literal

import httpx2

from agents_from_scratch.agent import (
    DEFAULT_MAX_TURNS,
    MODEL,
    RED,
    RESET,
    SYSTEM_PROMPT,
    LlmError,
    Message,
    llm_call,
    print_event,
    run_agent,
)
from agents_from_scratch.banner import print_banner, prompt_text

OLLAMA_URL = "http://host.docker.internal:11434"

type Mode = Literal["headless", "plain", "tui"]


def ollama_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(base_url=OLLAMA_URL, timeout=120)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument(
        "prompt", nargs="?", help="first message; opens the TUI with it already sent"
    )
    parser.add_argument(
        "-p",
        "--prompt",
        dest="headless_prompt",
        metavar="PROMPT",
        help="run PROMPT once without a UI and print the answer",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="use the line-based REPL instead of the TUI",
    )
    parser.add_argument(
        "-t", "--max-turns", default=DEFAULT_MAX_TURNS, type=int, help="max turns"
    )
    args = parser.parse_args(argv)
    if args.headless_prompt and args.plain:
        parser.error("-p and --plain cannot be combined")
    if args.prompt and (args.headless_prompt or args.plain):
        parser.error("a positional PROMPT is only for the TUI; use -p PROMPT instead")
    return args


def select_mode(args: argparse.Namespace) -> Mode:
    if args.headless_prompt:
        return "headless"
    return "plain" if args.plain else "tui"


async def run_headless(prompt: str, max_turns: int) -> None:
    async with ollama_client() as client:
        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            answer, _ = await run_agent(
                messages,
                max_turns=max_turns,
                call=partial(llm_call, client),
                on_event=print_event,
            )
        except LlmError as e:
            sys.exit(f"{RED}{e}{RESET}")  # one-shot: report and fail
        print("\n" + answer + "\n")


async def run_plain(max_turns: int) -> None:
    async with ollama_client() as client:
        call = partial(llm_call, client)
        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
        print_banner(MODEL)
        while True:
            prompt = input(prompt_text())
            if prompt == "exit":
                return
            messages.append({"role": "user", "content": prompt})
            try:
                answer, messages = await run_agent(
                    messages, max_turns=max_turns, call=call, on_event=print_event
                )
            except LlmError as e:
                # Keep the session: history is still valid, so the user can retry.
                print(f"{RED}{e}{RESET}")
                continue
            print("\n" + answer + "\n")


async def run_tui(max_turns: int, first_prompt: str | None) -> None:
    from agents_from_scratch.tui.app import AgentApp  # keeps Textual off the -p path

    async with ollama_client() as client:
        app = AgentApp(
            partial(llm_call, client),
            model=MODEL,
            max_turns=max_turns,
            first_prompt=first_prompt,
        )
        await app.run_async()


def cli(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    match select_mode(args):
        case "headless":
            asyncio.run(run_headless(args.headless_prompt, args.max_turns))
        case "plain":
            asyncio.run(run_plain(args.max_turns))
        case "tui":
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                sys.exit(
                    "The TUI needs an interactive terminal. "
                    "Use -p PROMPT for a one-shot run, or --plain for the REPL."
                )
            asyncio.run(run_tui(args.max_turns, args.prompt))


if __name__ == "__main__":
    cli()
