# Textual TUI

## Context

- Front end for the async agent loop (see `003_async_agent_loop.md`). Runs on the same asyncio loop; no threads.
- Reference layout: a screenshot of a similar agent TUI (conversation left, tools right, input bottom).
- The core imports nothing from the TUI. The TUI imports the core.

## Target layout (v1)

```
┌ Conversation ───────────────────────┐┌ Tools ───────────┐
│ [banner]                            ││ ● bash  ls -la   │
│ > user message (highlighted block)  ││ ● bash  pwd      │
│ assistant reply                     ││                  │
└─────────────────────────────────────┘└──────────────────┘
 Working... · 4.2s
┌ Message ────────────────────────────────────────────────┐
│ Send a message                                          │
└─────────────────────────────────────────────────────────┘
 Enter send · Tab tools · Ctrl+C exit
```

- Input at the bottom. Above it, a horizontal split: wide conversation on the left, narrow tools panel on the right.
- Banner is the first child of the conversation scroll, shown at start-up.
- Status bullet per tool call: **orange/yellow** = running, **green** = `returncode == 0`, **red** = non-zero or `timed_out`.
- The tools panel collapses with a key binding.

## Textual mapping

| Feature | Widgets / mechanism | Effort |
|---|---|---|
| Layout | `Horizontal(VerticalScroll#conversation, ToolPanel)`, then status `Static`, `Input` (or `TextArea`), `Footer`. CSS for sizes and borders. | Easy |
| Message blocks | One `Static`/`Markdown` per message, CSS class per role (`user`, `assistant`). Mounted into the conversation scroll. | Easy |
| Tool rows | `ToolRow` widget with a `status` reactive; CSS classes `running`/`ok`/`failed` color the bullet. | Easy |
| Collapse tools | Binding toggles a CSS class (`display: none` or width 0). `Collapsible` is an alternative. | Easy |
| Banner | `Static` at the top of the conversation. Reuse the existing banner code. | Easy |
| "Working… 4.2s" | `set_interval` in the UI while a turn runs. The core knows nothing about it. | Easy |
| Cancel turn (Esc) | Cancel the worker/task. Relies on the `finally` + `killpg` cleanup in the core. | Easy |

Textual limitations: no pixel graphics and no GUI-style mouse text selection. Neither is needed.

## How the TUI drives the loop

- The user submits a message, and the TUI starts `run_agent` as an async worker (`run_worker(..., exclusive=True)`).
- `run_agent` takes the message history and returns the new messages. It has no input loop, so the TUI owns the conversation state.
- The core emits events through an `on_event` callback. The callback runs on the same loop, so it can post Textual messages directly with no thread-safety handling.
- Events needed for v1:
  - `ToolStart(id, command)` adds a `ToolRow` in the running state.
  - `ToolEnd(id, BashResult)` sets the row to ok or failed.
  - `Final(text)` mounts the assistant message and clears the "Working" status.
  - `TurnStart` is optional and can drive the status line.
- Emit `ToolStart`/`ToolEnd` from inside each per-command coroutine, not after `gather`. That way each bullet changes color as its command finishes.
- Disable the input while a turn runs, or queue the message. Pick one and keep it simple.

## Requirements this puts on the core (changes to 003)

1. Events with a tool id move from *Later* to the next branch. `run_agent` should already accept an optional `on_event` so adding it doesn't change its shape.
2. Prefer an async HTTP client for `llm_call` over `asyncio.to_thread`. A cancelled `to_thread` call keeps running, so Esc would not stop the request. An async client cancels cleanly and allows streaming later.
3. `run_agent(history, ...) -> new messages`. No `input()` and no `print`.
4. `llm_call` and the tool runner are injectable. Tests use fakes, and Textual's `Pilot` can drive the app without a network.
5. LLM failures raise one core type, `LlmError` (see 003, *LLM failures*). The worker catches it, shows the message,
   and re-enables the input in `finally`. Required for v1: an uncaught exception in a Textual worker exits the whole
   app by default. Retries with a retry event come later.

## v2

| Feature | Notes | Effort |
|---|---|---|
| Inspect a tool call | Focusable or clickable `ToolRow`; opens a `ModalScreen` with the full command, stdout, stderr, return code. Needs `ToolEnd` to carry the full `BashResult`. | Easy to medium |
| Skills and prompt-templates area under the banner | UI is a `Static` list. Skills and templates must be implemented in the agent first. | UI trivial, agent side is the work |
| `@` file/folder picker | No built-in autocomplete. Build an `OptionList` overlay opened on the trigger character, or use `textual-autocomplete`. The agent needs a way to inject file contents. | Medium |
| `/` commands (toggle options, switch model) | Same overlay mechanism. The agent needs runtime-switchable config, so `llm_call` must be injectable. | Medium |
| Streaming and "hide reasoning" | Needs a streaming `llm_call` and token events. | Medium |

## Suggested order

1. Finish the async loop (003), including the async `llm_call`.
2. Add events (`ToolStart`, `ToolEnd`, `Final`) with a tool id. Test with fakes.
3. Static Textual layout: banner, input, empty panels, key bindings. No agent yet.
4. Wire `run_agent` as a worker. Show messages and tool rows with status colors.
5. Collapse, cancel (Esc) and the status timer.
6. v2 items one at a time.

## Open questions

- `Input` vs `TextArea`: the reference screenshot has multi-line input (Shift+Enter or Ctrl+J for a newline), which needs `TextArea`.
- Input behavior while a turn runs: disable or queue.
- Whether tool rows show the command only, or a one-line result summary as well.
