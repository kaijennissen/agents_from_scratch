"""Minimal regression tests for the agent's XML action parsing."""

import pytest

from agents_from_scratch.agent import parse_action, parse_xml


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
    ],
)
def test_parse_xml(tag: str, text: str, expected: list[str]) -> None:
    result = parse_xml(tag, text)
    assert len(result) == len(expected)
    assert set(result) == set(expected)


@pytest.mark.parametrize(
    "text,expected_key",
    [
        ("<bash> ls -alh </bash>", "bash"),
        ("<action><bash> ls </bash><exit> Finished! </exit></action>", "error"),
        ("<unknown> Finished! </unknown>", "exit"),
        ("<exit> Finished! </exit>", "exit"),
    ],
)
def test_parse_action(text: str, expected_key: str) -> None:
    """One action per turn is the contract; exit wins if the model breaks it."""
    keys = parse_action(text).keys()
    assert len(keys) == 1
    assert expected_key in keys
