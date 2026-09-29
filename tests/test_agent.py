"""Minimal regression tests for the agent's XML action parsing."""

from agents_from_scratch.agent import parse_action, parse_xml


def test_parse_xml_returns_stripped_contents_in_order() -> None:
    text = "<action><bash> ls </bash><bash>pwd</bash></action>"

    assert parse_xml("bash", text) == ["ls", "pwd"]
    assert parse_xml("exit", text) == []


def test_parse_action_buckets_each_tag() -> None:
    text = (
        "<action><bash>ls</bash><message>thinking</message><exit>done</exit></action>"
    )

    assert parse_action(text) == {
        "bash": ["ls"],
        "message": ["thinking"],
        "exit": ["done"],
    }
