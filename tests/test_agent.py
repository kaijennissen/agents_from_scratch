"""Regression tests for the agent's XML action parsing and the LLM call."""

import json
from collections.abc import Callable

import httpx2
import pytest
from httpx2 import AsyncClient

from agents_from_scratch.agent import (
    MIXED_ACTIONS_ERROR,
    MODEL,
    LlmError,
    Message,
    llm_call,
    parse_action,
    parse_xml,
)


@pytest.mark.parametrize(
    "tag,text,expected",
    [
        ("bash", "<bash> ls -alh </bash>", ["ls -alh"]),
        ("bash", "<action><bash> ls </bash><bash>pwd</bash></action>", ["ls", "pwd"]),
        ("exit", "<exit> Finished! </exit>", ["Finished!"]),
        (
            "action",
            "<action><bash> ls </bash><bash>pwd</bash></action>",
            ["<bash> ls </bash><bash>pwd</bash>"],
        ),
        ("bash", "<bash>\n  cd src &&\n  ls\n</bash>", ["cd src &&\n  ls"]),
        ("bash", "<exit>done</exit>", []),
        ("bash", "<bash>ls", []),
        ("bash", "<bash></bash>", [""]),  # pins current behaviour, not a wish
    ],
)
def test_parse_xml(tag: str, text: str, expected: list[str]) -> None:
    """Contents come back in order of appearance, stripped at the edges only."""
    assert parse_xml(tag, text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<bash>ls</bash><bash>pwd</bash>", {"bash": ["ls", "pwd"]}),
        ("<exit> done </exit>", {"exit": ["done"]}),
        ("<unknown> Finished! </unknown>", {"exit": ["No action"]}),
        ("Sure!\n<action><bash>ls</bash></action>\nHope it helps.", {"bash": ["ls"]}),
        ("<bash>ls</bash><exit>done</exit>", {"error": [MIXED_ACTIONS_ERROR]}),
        ("<exit>done</exit><bash>ls</bash>", {"error": [MIXED_ACTIONS_ERROR]}),
    ],
)
def test_parse_action(text: str, expected: dict[str, list[str]]) -> None:
    """One action type per turn; mixing is an error, an unknown reply a clean exit."""
    assert parse_action(text) == expected


def fake_ollama(handler: Callable[[httpx2.Request], httpx2.Response]) -> AsyncClient:
    return AsyncClient(
        transport=httpx2.MockTransport(handler), base_url="http://ollama"
    )


async def test_llm_call_posts_history_and_returns_reply() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"message": {"content": "<exit>hi</exit>"}})

    messages: list[Message] = [{"role": "user", "content": "hello"}]
    async with fake_ollama(handler) as client:
        reply = await llm_call(client, messages)

    assert reply == "<exit>hi</exit>"
    assert requests[0].url.path == "/api/chat"
    assert json.loads(requests[0].content) == {
        "model": MODEL,
        "stream": False,
        "messages": messages,
    }


@pytest.mark.parametrize(
    "reply,expected",
    [
        (
            httpx2.Response(404, json={"error": "model 'x' not found"}),
            "model 'x' not found",
        ),
        (httpx2.Response(502, text="Bad Gateway"), "Bad Gateway"),
        (
            httpx2.ConnectError("All connection attempts failed"),
            "All connection attempts failed",
        ),
        (httpx2.Response(200, json={"unexpected": "shape"}), "Unexpected reply"),
    ],
)
async def test_llm_call_turns_failures_into_llm_error(
    reply: httpx2.Response | Exception, expected: str
) -> None:
    """Front ends catch one error type, and its message is readable for the user."""

    def handler(_: httpx2.Request) -> httpx2.Response:
        if isinstance(reply, Exception):
            raise reply
        return reply

    async with fake_ollama(handler) as client:
        with pytest.raises(LlmError, match=expected):
            await llm_call(client, [])
