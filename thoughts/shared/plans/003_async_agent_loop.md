# Async agent loop

## Context

- **Learning project.** Work step by step and understand each piece before moving on.
- Long-term goal: one agent loop that runs **headless (CLI)** and **with a TUI (Textual)**, with a decoupled design.
- The TUI on `feat/tui` is a throw-away draft (sync loop in a thread, `on_event` callback) and can be reshaped.
  Textual and workers are out of scope for this branch.

## Goal of this branch (`async_tool_calls`)

Make `run_agent` a **coroutine**, in a shape that fits the TUI later. **No callbacks or events yet.**

- `run_agent` is `async`. The CLI calls `asyncio.run(...)` once; the core never does.
- `llm_call` is a coroutine too, so it doesn't block the loop (the UI will share the loop).
- All `<bash>` tags of one turn run concurrently (`asyncio.gather`); the next LLM call waits for every result.
- No `print` or `input` in the core (`input()` goes away with the TUI).

## Tool execution (prototype: `async_experiments.py`)

- `create_subprocess_shell(..., start_new_session=True)`, with `wait_for` around `communicate()`.
- `finally`: `os.killpg(proc.pid, SIGKILL)` (swallow `ProcessLookupError`), then `await proc.wait()`.
  Never turn `CancelledError` into a return value.
- Result: frozen dataclass `BashResult(stdout, stderr, returncode, timed_out)` with `completed()` / `timeout()`
  factories. Invariant: `timed_out <=> returncode is None`.
- `format_observation(cmd, result)` produces the text the model reads, always showing both streams.
- System prompt must say that commands in one action run **in parallel** and must be independent; chain with `&&`.

## Open decisions

- Module split (tools / core / cli) and where `BashResult`, `run`, `format_observation` live.
- `TIMEOUT` value and owner; `MAX_OUTPUT_CHARS` (formatter, per stream?).
- Async `llm_call`: `asyncio.to_thread(...)` vs. an async HTTP client (check what `httpx2` offers).
- Pass `llm_call` and the tool runner into `run_agent` as arguments, so tests can use fakes.

## Later (not this branch)

- Events from the loop (`TurnStart`, `ToolStart`, `ToolEnd`, `Final`) with a tool id; `ToolEnd` per command as it finishes.
- TUI as a front end on the same loop (Textual worker); cancelling a turn relies on the `finally` cleanup.
- Partial output on timeout: read the streams into our own buffers.
- Persistent shell state (e.g. working directory).

## Rule for the core

The core imports nothing from the CLI, TUI or banner code. Front ends import the core.
