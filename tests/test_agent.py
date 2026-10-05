"""The act-observe-decide loop and the action protocol it speaks."""

from __future__ import annotations

import io

import pytest

from agents_from_scratch import agent
from agents_from_scratch.agent import parse_action, parse_xml
from agents_from_scratch.agent_log import configure_logging
from conftest import FakeLLM, bash, exit_


def test_parse_xml_returns_stripped_contents_in_order() -> None:
    text = "<action><bash> ls </bash><bash>pwd</bash></action>"

    assert parse_xml("bash", text) == ["ls", "pwd"]
    assert parse_xml("exit", text) == []


def test_parse_action_extracts_single_tag() -> None:
    text = "<action>\n<bash>ls -alh src</bash>\n</action>"

    assert parse_action(text) == {"bash": "ls -alh src"}


def test_parse_action_prefers_exit_over_bash() -> None:
    """One action per turn is the contract; exit wins if the model breaks it."""
    text = "<action><bash>ls</bash><exit>done</exit></action>"

    assert parse_action(text) == {"exit": "done"}


def test_parse_action_empty_when_no_known_tag() -> None:
    assert parse_action("<action><think>hmm</think></action>") == {}
    assert parse_action("I would just run ls, if I could.") == {}


def test_loop_acts_observes_and_exits() -> None:
    out = io.StringIO()
    llm = FakeLLM(bash("echo observed"), exit_("all good"))
    answer = agent.main(
        "go", log=configure_logging(stream=out, color=False), call_llm=llm
    )

    assert answer == "all good"
    transcript = out.getvalue()
    assert "$ echo observed" in transcript
    assert "observed" in transcript
    assert "2 turns · 2584 tok" in transcript  # 2 x (1204 + 88)
    assert "messages=" not in transcript  # debug-only event


def test_loop_sends_the_tool_result_back_as_the_next_observation() -> None:
    llm = FakeLLM(bash("echo observed"), exit_("all good"))
    agent.main(
        "go", log=configure_logging(stream=io.StringIO(), color=False), call_llm=llm
    )

    assistant, observation = llm.seen[1][-2:]
    assert assistant["role"] == "assistant"
    assert observation == {
        "role": "user",
        "content": "Output of `$ echo observed`:\nobserved\n\n(exit code 0)",
    }


def test_loop_survives_a_reply_without_an_action() -> None:
    out = io.StringIO()
    llm = FakeLLM("I would rather chat.", exit_("fine"))
    answer = agent.main(
        "go", log=configure_logging(stream=out, color=False), call_llm=llm
    )

    assert answer == "fine"
    assert "unparsed · I would rather chat." in out.getvalue()
    assert "🧩 parse" in out.getvalue()


def test_loop_reports_a_hanging_command_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "COMMAND_TIMEOUT", 1)
    out = io.StringIO()
    llm = FakeLLM(bash("sleep 5"), exit_("never mind"))
    answer = agent.main(
        "go", log=configure_logging(stream=out, color=False), call_llm=llm
    )

    assert answer == "never mind"
    assert "✗ · rc=124" in out.getvalue()
    assert "timed out" in out.getvalue()


def test_loop_reports_when_it_runs_out_of_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "MAX_TURNS", 2)
    out = io.StringIO()
    llm = FakeLLM(*[bash("echo loop") for _ in range(2)])
    answer = agent.main(
        "go", log=configure_logging(stream=out, color=False), call_llm=llm
    )

    assert answer == "Ran out of turns (2) without an <exit> action."
    assert "🎯 done   Ran out of turns (2)" in out.getvalue()
    assert "2 turns" in out.getvalue()


def test_loop_shows_the_model_its_unusable_reply() -> None:
    llm = FakeLLM("I would rather chat.", exit_("fine"))
    agent.main(
        "go", log=configure_logging(stream=io.StringIO(), color=False), call_llm=llm
    )

    asked = llm.seen[1][-1]
    assert asked["role"] == "user"
    assert asked["content"].endswith("I would rather chat.")
