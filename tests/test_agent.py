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
def test_parse_xml_returns_stripped_contents_in_order(
    tag: str, text: str, expected: list[str]
) -> None:
    result = parse_xml(tag, text)
    assert len(result) == len(expected)
    assert set(result) == set(expected)


def test_parse_action_extracts_single_tag() -> None:
    text = "<action>\n<bash>ls -alh src</bash>\n</action>"

    assert parse_action(text) == {"bash": "ls -alh src"}


def test_parse_action_prefers_exit_over_bash() -> None:
    """One action per turn is the contract; exit wins if the model breaks it."""

    text = "<action><bash>ls</bash><exit>done</exit></action>"

    assert parse_action(text) == {"exit": "done"}


def test_parse_action_empty_when_no_known_tag() -> None:
    assert parse_action("<action><think>hmm</think></action>") == {"exit": "No action"}
    assert parse_action("I would just run ls, if I could.") == {"exit": "No action"}
