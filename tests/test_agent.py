"""Regression tests for the agent's XML action parsing."""

import pytest

from agents_from_scratch.agent import MIXED_ACTIONS_ERROR, parse_action, parse_xml


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
