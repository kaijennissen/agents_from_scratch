"""Shared doubles for the agent tests."""

from __future__ import annotations

from agents_from_scratch.agent import LLMResponse, Message


class FakeLLM:
    """Replays canned replies with fixed accounting, the way a local model would."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.seen: list[list[Message]] = []

    def __call__(self, messages: list[Message]) -> LLMResponse:
        self.seen.append(list(messages))  # copy: the loop keeps appending
        content = self.replies.pop(0)
        return LLMResponse(content=content, prompt_tokens=1204, tokens=88, ms=1900)


def bash(cmd: str) -> str:
    return f"<action><bash>{cmd}</bash></action>"


def exit_(text: str) -> str:
    return f"<action><exit>{text}</exit></action>"
