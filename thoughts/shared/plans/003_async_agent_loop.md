# Async agent loop

## Context

- **Learning project.** Work step by step and understand each piece before moving on.
- Long-term goal: one agent loop that runs **headless (CLI)** and **with a TUI (Textual)**, with a decoupled design.
  See `004_textual_tui.md` for the TUI.
- The TUI on `feat/tui` is a throw-away draft (sync loop in a thread, `on_event` callback) and can be reshaped.
  Textual and workers are out of scope for this branch.

## Goal of this branch (`async_tool_calls`)

Make `run_agent` a **coroutine** with an **`on_event` callback**, in a shape that fits the TUI later.

- `run_agent` is `async`. The CLI calls `asyncio.run(...)` once; the core never does.
- `llm_call` is a coroutine that uses a shared `httpx2.AsyncClient` (`httpx2.AsyncClient` exists, checked).
  The client is created once by the caller and passed in. It is not created inside the core.
- All `<bash>` tags of one turn run concurrently (`asyncio.gather`); the next LLM call waits for every result.
- The tool runner is passed in as well (`run_tool`), so tests can use fakes with no subprocesses.
- Progress is reported through **one `on_event(event)` callback** with typed event dataclasses. The core has no `print` or `input`.
- `input()` goes away with the TUI. Until then the CLI loop lives in the CLI, not in the core.

## Shape of `run_agent` (pseudo-code)

```python
# events.py (core): frozen dataclasses, each tool event carries an id
@dataclass(frozen=True)
class TurnStart:  turn: int; max_turns: int
@dataclass(frozen=True)
class ToolStart:  id: tuple[int, int]; command: str          # id = (turn, index)
@dataclass(frozen=True)
class ToolEnd:    id: tuple[int, int]; command: str; result: BashResult | None  # None = cancelled
Event = TurnStart | ToolStart | ToolEnd

type OnEvent  = Callable[[Event], None]                      # plain def, must not block
type RunTool  = Callable[[str], Awaitable[BashResult]]
type LlmCall  = Callable[[list[Message]], Awaitable[str]]

# core
class LlmError(Exception): ...                                # message is meant for the user

async def llm_call(client: httpx2.AsyncClient, messages) -> str:
    # network error, 4xx/5xx or malformed reply -> raise LlmError(...) from e
    r = await client.post(ENDPOINT, json={...})
    return r.json()["message"]["content"]

async def run_agent(
    messages: list[Message],
    max_turns: int,
    *,
    llm_call: LlmCall,          # e.g. functools.partial(llm_call, client)
    run_tool: RunTool = run,    # from async_experiments.py
    on_event: OnEvent = lambda e: None,
) -> tuple[str, list[Message]]:
    for turn in range(max_turns):
        emit(on_event, TurnStart(turn, max_turns))
        response = await llm_call(messages)
        action = parse_action(response)

        if "exit" in action:
            messages.append(assistant(response))
            return action["exit"][0], messages
        if "error" in action:
            messages += [assistant(response), user(action["error"][0])]
            continue

        # bash: run all commands concurrently; events fire per command as it finishes
        async def one(i: int, cmd: str) -> str:
            id = (turn, i)
            emit(on_event, ToolStart(id, cmd))
            result = None                                    # stays None if cancelled
            try:
                result = await run_tool(cmd)
                return format_observation(cmd, result)
            finally:                                         # also runs on cancellation
                emit(on_event, ToolEnd(id, cmd, result))

        observations = await asyncio.gather(*(one(i, c) for i, c in enumerate(action["bash"])))
        # assistant message and observations are appended together AFTER the tools finish,
        # so a cancel never leaves a <bash> request without observations in the history
        messages += [assistant(response), user("\n\n".join(observations))]

    return f"Ran out of turns ({max_turns}) without an <exit> action.", messages


def emit(on_event, event):
    try:
        on_event(event)
    except Exception:
        pass            # a broken front end must not kill the agent (log it later)
```

How it is used (the same core, two front ends):

```python
# CLI (headless): on_event prints; the client lives for one asyncio.run
async def amain(prompt, max_turns):
    async with httpx2.AsyncClient(timeout=120) as client:
        answer, _ = await run_agent(msgs, max_turns,
                                    llm_call=partial(llm_call, client),
                                    on_event=print_event)

# TUI (later): runs on Textual's event loop, so on_event can touch widgets directly
class AgentApp(App):
    async def on_mount(self):   self.client = httpx2.AsyncClient(timeout=120)
    async def on_unmount(self): await self.client.aclose()

    def on_event(self, ev):
        match ev:
            case ToolStart(id, cmd):         self.tools.add_row(id, cmd)      # orange bullet
            case ToolEnd(id, _, result):     self.tools.finish_row(id, result)  # green / red

    @work(exclusive=True)
    async def submit(self, text):
        try:
            answer, self.messages = await run_agent(self.messages, 25,
                                                    llm_call=partial(llm_call, self.client),
                                                    on_event=self.on_event)
        except LlmError as e:
            self.show_error(e)
        finally:
            self.clear_working_status()
```

## Why the callback is decoupled enough

- The core only calls a function it was given. It knows nothing about Textual, `print`, or widgets.
- A Textual `@work` coroutine runs on the **same event loop** as the UI, so `on_event` can call widget methods
  directly. No `post_message` or `call_from_thread` is needed. Thread workers would need `call_from_thread`.
- The headless CLI is just a different `on_event` (it prints). That is the proof the core is decoupled.

## Rules for events and the callback

- **One callback, typed events**, not one callback per task. Each tool event has an `id` because `gather`
  completes in a different order than the commands were issued.
- **Emit inside the per-command coroutine**, not after `gather`. Otherwise all bullets change color at the same time.
- The callback is a plain `def` and must return immediately. `emit()` swallows its exceptions.
- `ToolEnd` is sent from `finally`, so a **cancelled** command still ends its row (`result=None`, shown as cancelled/red).
  Otherwise the bullet stays orange forever.
- **Cancelling a turn** relies on the `finally` cleanup in `run` (killpg + `await proc.wait()`).
  Never turn `CancelledError` into a return value.
- **History stays consistent on cancel**: append the assistant message and its observations together, after the tools
  finish (see pseudo-code).
- **LLM errors raise out of `run_agent`.** The caller (CLI or TUI worker) catches them and shows them. The TUI must
  clear its "Working…" status in `finally`.

## LLM failures

A failed LLM call (model unavailable, network down, server error) is shown to the user and never ends the session.
The user can retry later or, in the future, pick another model.

- **One error type: `LlmError`** (core). The provider turns every failure into it with `raise LlmError(...) from e`:
  `httpx2.HTTPError` (network, timeout), non-2xx status, and malformed replies. Front ends catch only `LlmError`
  and need no knowledge of httpx or the provider. The message is readable as is (Ollama's `{"error": ...}` text
  when available, e.g. "model 'x' not found").
- **Cancellation is not an error.** `asyncio.CancelledError` is a `BaseException`, so `except LlmError` (or even
  `except Exception`) never swallows Esc.
- **Retrying is free for the history.** A failed call happens before anything of that turn is appended, so the
  history stays valid and the same `run_agent(messages)` can simply run again.
- CLI: interactive mode prints the error and keeps the session; `-p` prints it and exits non-zero.

### Retries (later, not needed for TUI v1)

`main` retries 3 times with exponential backoff. Port it with these changes:

- Retry only transient failures: transport errors (connect, timeout), 5xx, 429. Other 4xx (404 = model not found,
  401) fail the same way again and are raised at once.
- Wait with `await asyncio.sleep`, never `time.sleep` (it would freeze the TUI and ignore cancel).
- Each retry is reported as an event (e.g. `LlmRetry(attempt, error, delay)`), so the user sees why nothing happens.
- Delays are a parameter, so tests don't wait.

Open: where the retry loop lives.

- **Inside `llm_call`:** simplest, and it sees status codes to decide what is retryable. But it then needs
  `on_event`, and every new provider repeats the loop.
- **Wrapper `with_retries(call, on_event, delays) -> LlmCall`:** provider stays thin, loop and event are written once
  and testable with a fake `LlmCall`. Needs the provider to say what is retryable, e.g. `LlmError(..., retryable=True)`.
- Leaning: inside `llm_call` while there is one provider; move to the wrapper together with `providers.py`.

## Tool execution (prototype: `async_experiments.py`)

- `create_subprocess_shell(..., start_new_session=True)`, with `wait_for` around `communicate()`.
- `finally`: `os.killpg(proc.pid, SIGKILL)` (swallow `ProcessLookupError`), then `await proc.wait()`.
  Never turn `CancelledError` into a return value.
- Result: frozen dataclass `BashResult(stdout, stderr, returncode, timed_out)` with `completed()` / `timeout()`
  factories. Invariant: `timed_out <=> returncode is None`.
- `format_observation(cmd, result)` produces the text the model reads, always showing both streams.
- Status mapping for the UI: running between `ToolStart` and `ToolEnd`; green for `returncode == 0`;
  red for non-zero, `timed_out`, or cancelled.
- System prompt must say that commands in one action run **in parallel** and must be independent; chain with `&&`.
  (The current prompt says "executed in turn" and must change.)

## Module layout

**Decision:** a `core/` package, so the dependency rule is visible in the import paths (and can be linted later).

```
src/agents_from_scratch/
  core/
    __init__.py
    agent.py      # run_agent, parse_action, SYSTEM_PROMPT, llm_call
    events.py     # TurnStart, ToolStart, ToolEnd, Event, OnEvent
    tools.py      # BashResult, run, format_observation, TIMEOUT   (from async_experiments.py)
    providers.py  # later: one factory per backend that returns an LlmCall
  cli.py          # front end: argparse, print_event, asyncio.run, input loop
  tui.py          # front end: Textual App (later, see 004)
  banner.py       # shared by cli and tui
  __main__.py     # calls cli.cli()
```

- `tools.py` and `events.py` are separate so that `BashResult` is imported by both events and the loop without a
  circular import or a bloated `agent.py`.
- **Dependency direction:** `cli` and `tui` import from `core` and `banner`. Inside `core`, `agent` imports `events` and `tools`.
  Nothing in `core` imports `cli`, `tui` or `banner`.
- **`banner.py`:** `render_banner(model, color)` already returns a string, so the CLI prints it and the TUI can render
  it with `rich.text.Text.from_ansi(...)` into a `Static`. `print_banner`, `prompt_text` and `use_color` are
  terminal-only and are used by the CLI only. `GREY`/`RESET` are no longer needed by the core (printing moves to `print_event`).
- `__main__.py` and the entry point move from `agent.cli` to `cli.cli`.

## Provider abstraction (later, not this branch)

The seam is the `LlmCall` argument of `run_agent`: `Callable[[list[Message]], Awaitable[str]]`.
A provider is a factory that returns such a callable. `run_agent` does not change.

```python
# providers.py
def ollama(client, model, endpoint) -> LlmCall: ...       # POST /api/chat       -> message.content
def openrouter(client, model, api_key) -> LlmCall: ...    # POST /chat/completions -> choices[0].message.content
```

- Each factory hides the differences in URL, auth header, request fields and response shape.
- A `Protocol` or class is only worth it when a provider needs more than one function (streaming, model list, token counts).
- The same seam later gives `/` model switching in the TUI: swap the callable, keep `run_agent`.
- This branch: keep `llm_call` in `agent.py` and Ollama only. Move it to `providers.py` when the second backend arrives.

## Changes needed in the current `agent.py`

- `llm_call`: `httpx2.post` becomes `await client.post(...)` on a passed-in `AsyncClient`.
- `subprocess.run(... stderr=STDOUT ...)` is replaced by `run_tool` returning a `BashResult` (separate streams).
- `MAX_OUTPUT_CHARS` truncation moves into `format_observation`.
- `timeout=120` becomes `TIMEOUT`, which needs a sensible value (it is 2 in the experiment).
- The `print` calls for the turn counter and `$ command` become events.
- `main`, `cli`, `input()` loop and `print` of the answer move to `cli.py`, outside the core.
- The `banner` import moves out of `agent.py`.
- System prompt: parallel execution, as above.

## Open decisions

- Module layout: decided (`core/` package). Open: when to move `llm_call` to `providers.py`.
- `TIMEOUT` value and owner; `MAX_OUTPUT_CHARS` (formatter, per stream?).
- Tool id: `(turn, index)` tuple vs. a counter/uuid.
- Whether `llm_call` is passed as a partial (as above) or `run_agent` takes `client` and calls `llm_call` itself.
- Whether events land on this branch or the next. The `on_event` parameter should exist now so its shape doesn't change later.
- Tests: fake `llm_call` and `run_tool`; or `httpx2.MockTransport` for the client (exists in `httpx2`).

## Later (not this branch)

- TUI as a front end on the same loop (Textual worker); see `004_textual_tui.md`.
- Partial output on timeout: read the streams into our own buffers (notes in `async_experiments.py`).
- Streaming `llm_call` (tokens, reasoning toggle).
- Persistent shell state (e.g. working directory).
- A tool runner that raises instead of returning a `BashResult` (not a failed command, which is a normal result,
  but Python failing to start it, e.g. `ValueError` for a null byte in the command). Today the row gets no end event,
  `gather` aborts the turn, and sibling tools keep running unawaited. Options: catch in `run_tool` and emit a
  `ToolFailed` event with an observation for the model, or a `TaskGroup` that cancels the siblings.

## Rule for the core

The `core/` package imports nothing from the CLI, TUI or banner code. Front ends import `core`.
(Today `agent.py` imports `banner`. That import moves to `cli.py`.)
