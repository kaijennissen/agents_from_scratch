import asyncio
import os
import signal
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from agents_from_scratch.banner import RESET, rgb

TIMEOUT = 3


RED = rgb("#FF5555")
GREEN = rgb("#50FA7B")
YELLOW = rgb("#FFCC00")


@dataclass(frozen=True)
class BashResult:
    cmd: str
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool

    @classmethod
    def completed(cls, cmd: str, stdout: str, stderr: str, returncode: int) -> Self:
        return cls(cmd, stdout, stderr, returncode, timed_out=False)

    @classmethod
    def timeout(cls, cmd: str, stdout: str = "", stderr: str = "") -> Self:
        return cls(cmd, stdout, stderr, returncode=None, timed_out=True)


@dataclass(frozen=True, kw_only=True)
class BashCall:
    id: str
    cmd: str


@dataclass(frozen=True, kw_only=True)
class SkillCall:
    id: str
    name: str


type ToolCall = BashCall | SkillCall


@dataclass(frozen=True)
class ToolStart:
    call: ToolCall


@dataclass(frozen=True)
class ToolEnd:
    call: ToolCall
    result: BashResult | None


type ToolEvent = ToolStart | ToolEnd


def format_observation(result: BashResult) -> str:
    """Turn a BashResult into the text the model reads."""
    if result.timed_out:
        return (
            f"Command `{result.cmd}` was killed after a timeout of {TIMEOUT} seconds. "
            "It did not finish, so its result and side effects are unknown, "
            "and any output it produced was discarded."
        )
    return (
        f"Command `{result.cmd}` finished with exit code {result.returncode}.\n"
        f'stdout: "{result.stdout}"\n'
        f'stderr: "{result.stderr}"'
    )


def on_event_callback(event: ToolEvent):
    match event:
        case ToolStart():
            print(f"{YELLOW}running: {event.call.cmd}{RESET}")
        case ToolEnd():
            if event.result.returncode == 0:
                print(f"{GREEN}success: {event.call.cmd}{RESET}")
            elif event.result.returncode == 1:
                print(f"{RED}failure: {event.call.cmd}{RESET}")
        case _:
            print(f"{RED}don't know: {event.cmd}{RESET}")


def on_event(event: str, cmd: str) -> None:
    if event == "success":
        print(f"{GREEN}success: {cmd}{RESET}")
    elif event == "failure":
        print(f"{RED}failure: {cmd}{RESET}")
    else:
        print(f"{YELLOW}running: {cmd}{RESET}")


async def run_bash_tool(cmd: str):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    proc_id = proc.pid

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        return BashResult.completed(
            cmd=cmd,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            returncode=proc.returncode,
        )

    except TimeoutError:
        return BashResult.timeout(cmd)

    finally:
        try:
            os.killpg(proc_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


# TODO: finish the Tool-class


# TODO: write a run_tool function that wraps on_event and tool-call
# pass dataclasses to on_event instead of strings
async def run_tool(
    tool_call: ToolCall,
    tool_fn: Callable[ToolEvent, None],
    on_event: Callable[ToolEvent, None] = lambda: None,
):
    on_event(ToolStart(call=tool_call))
    result = await tool_fn(tool_call.cmd)
    on_event(ToolEnd(call=tool_call, result=result))
    return result


# on_event()
#    tool_call()
#    on_event()


def create_uuid():
    return str(uuid.uuid4()).split("-")[0]


async def main():
    cmds = ["for i in 1 2 3 4 5;do echo $i; sleep $i; done", "ls -alh", "ls -alh priv"]
    tool_calls = [BashCall(id=create_uuid(), cmd=cmd) for cmd in cmds]
    results = await asyncio.gather(
        *(
            run_tool(
                tool_call=tool_call, tool_fn=run_bash_tool, on_event=on_event_callback
            )
            for tool_call in tool_calls
        )
    )
    for result in results:
        print(format_observation(result), end="\n\n")


if __name__ == "__main__":
    asyncio.run(main())


# Next Session:
# What this means for your design
# To keep partial output, reading has to happen in a buffer that you own. That buffer has to outlive the cancelled coroutine. Something like this, in words:

# 1. Create two lists (or bytearrays) outside the timed section.
# 2. Start a reader coroutine per stream. Each reads chunks from proc.stdout or proc.stderr and appends them to its list until EOF.
# 3. Wrap gather(read_out, read_err, proc.wait()) in wait_for.
# 4. On timeout, the lists still hold everything read so far, because they live outside the cancelled coroutine.
#
# Questions before you write it
# 1. Which StreamReader method fits the reader loop? Compare readline(), read(n) and read(). What does each do when the command prints a long line without a newline, or
#    prints a huge amount of data?
# 2. How does the reader know when to stop? What does read(n) return at EOF?
# 3. After killpg, do the pipes reach EOF? Think about a background child that survived. Is the kill in finally enough, or does it also matter that it kills the whole
#    group?
# 4. Do you still need the call to await proc.wait() inside the gather, or is it enough to call it in finally?
#
# Prove it for yourself before writing the real version. In a throwaway script, create a list and a small reader loop for proc.stdout, then time it out with wait_for on
# the same loop command. Check that the list contains 1 and 2. Then say how you'd put this into run.

# Learnings:
# - PID: process ID
# - PPID: parent process ID
# - PGID: process group ID

# - start_new_session=False -> the process will inherit the PGID of the python script
# - passing 'sleep 100 && sleep 101' as cmd to create_subprocess_shell starts /bin/sh, and /bin/sh starts the
#   sleep commands as its child processes, one after the other: 'sleep 101' only starts once 'sleep 100' has
#   exited with code 0 (that is what && does). So at any moment there is the shell plus at most one sleep
#   (some shells replace themselves with the last command, so the shell may disappear during 'sleep 101').
#   The PID (process ID) we get back from create_subprocess_shell belongs to the shell only; the PIDs of the sleeps are unknown.
#   To cancel all of them in case of a timeout (wait_for) we need to signal the PGID , not a PID
# - start_new_session=True -> /bin/sh is started with a new PGID (equal to its own PID) and its child processes inherit it; this allows to terminate them via os.killpg(proc.pid, ...)
# - signal.SIGTERM: asks the process to stop; it can catch the signal to clean up first, or ignore it.
# - signal.SIGKILL: the OS ends the process immediately; it cannot be caught or ignored, so there is no cleanup.
# - ProcessLookupError: the process we want to kill may already be gone. We catch the error, because
#   we only care that nothing is left running.


# ---------------------------------------------------------------------------
# To review later (added from the discussion)
# ---------------------------------------------------------------------------

# Async concepts
# - wait_for cancels the awaiting coroutine. It does NOT kill the OS process; we have to do that ourselves.
# - wait_for must wrap communicate(), not create_subprocess_shell(...). Spawning takes milliseconds,
#   so a timeout around it would never fire.
# - proc.kill() / proc.terminate() are plain methods (not coroutines) and only send a signal.
#   `await proc.wait()` confirms the process exited and reaps it, so it does not stay a zombie.
# - finally runs on every exit path, including cancellation. Never turn CancelledError into a return value;
#   if it is caught, re-raise it.
# - gather returns results in the order the coroutines were passed in, not the order they finish.
#   A turn takes as long as its slowest command (max), not the sum of all commands.

# Process details
# - killpg without start_new_session=True would also kill Python and `uv run` (same process group).
# - A background child (`sleep 100 &`) inherits the stdout/stderr pipes, so communicate() blocks until the
#   child exits, even though the shell has finished. That is why the kill in `finally` is unconditional.
# - Process groups are only a default: a daemon can leave its group (setsid/setpgid), and killpg cannot reach it.
# - After SIGKILL, proc.returncode is -9. On a timeout we set returncode=None on purpose, because -9 comes
#   from our own kill and not from the command.

# Design decisions (and why)
# - stdout, stderr and the exit code are independent of each other. format_observation always shows both
#   streams, so the model can tell "no output" from "output missing".
# - A timeout is a returned value (an expected outcome). The command's result and side effects are unknown.
# - Dataclass with timeout()/completed() factories instead of a TypedDict: neither checks types at runtime;
#   the dataclass catches forgotten fields, and the factories keep `timed_out <=> returncode is None` in one place.
# - A pipe (a | b) runs both sides at the same time. For ordering use `&&`. The system prompt must say this
#   once commands in one action run in parallel.
# - Option A (asyncio.run per turn) vs. B (whole loop async): both work. A blocking llm_call is harmless in
#   either, because nothing else is in flight at that point.

# Known limitation
# - On a timeout, partial output is lost because communicate() is cancelled. Keeping it would mean reading
#   proc.stdout / proc.stderr ourselves.


# ---------------------------------------------------------------------------
# Shell operators: one after the other vs. all at once
# ---------------------------------------------------------------------------

# One after the other (sequential):
# - a ; b    run b after a finishes, whatever a's exit code was
# - a && b   run b only if a succeeded (exit code 0)   -> use for "do this, then that"
# - a || b   run b only if a failed (exit code != 0)   -> fallback

# At the same time (concurrent):
# - a | b    pipe: start a and b together; a's stdout is b's stdin. Passes data, does NOT order the commands.
#            (the exit code of the pipeline is the exit code of b, unless `set -o pipefail`)
# - a & b    start a in the background, the shell moves on to b immediately without waiting for a.
#            A trailing `&` (`a &`) leaves a running after the shell exits.

# Other special characters:
# - $VAR, $(cmd)   variable / command substitution (expanded by the shell, before the command runs)
# - * ? {1..3}     globbing / brace expansion (the latter is a bash feature, not POSIX sh)
# - > file, >> file, 2> file, 2>&1   redirect stdout (overwrite / append), stderr, or stderr into stdout
# - < file         read stdin from a file
# - ( a; b )       run a group in a subshell
# - 'text' "text"  quoting: single = literal, double = $ expansions still happen

# Why it matters here: commands in one <bash> action run concurrently (gather), so they must be independent.
# If b depends on a, combine them in ONE command with && (e.g. `mkdir foo && touch foo/a`).
# Check the difference: `time (sleep 2 | sleep 2)` ~2s, `time (sleep 2 && sleep 2)` ~4s.


# ---------------------------------------------------------------------------
# Async function vs. coroutine (and how to type them)
# ---------------------------------------------------------------------------

# Vocabulary (say "async function", not "coroutine function")
# - Async function: anything defined with `async def`, e.g. llm_call.
#   `call = partial(llm_call, client)` is also an async function, with the client already filled in.
# - Coroutine: the object you get when you CALL an async function, e.g. `call(messages)`.
#   Calling does not run the body. The body only runs when the coroutine is awaited.
# - Rule: "async function" = the thing you call, "coroutine" = the thing you await.
#   Test: if you can put (...) after it, it is a function. A coroutine can only be awaited, not called.
# - `await call(messages)`: await applies to `call(messages)` (with the parentheses), never to `call` alone.
# - Bug from this session: `cli()` was called but never awaited -> "coroutine 'cli' was never awaited".
#   Fix: a normal `def cli()` that calls `asyncio.run(main(...))` once.

# Types
# - `call` (the async function):  Callable[[list[Message]], Awaitable[str]]
# - `call(messages)` (the coroutine) is described by the second part: Awaitable[str]
# - `await call(messages)` is a str
# - Coroutine[YieldType, SendType, ReturnType] describes only the coroutine, never the async function.
#   Yield/send = how the event loop suspends and resumes it (implementation detail, usually Any, Any).
#   Return = what `await` gives back. That is the only slot that matters in our code.
#   Writing only two parameters leaves the return type Unknown (that was the pyright error).
# - run_agent takes `Awaitable[str]` and not Coroutine[Any, Any, str]: it only needs to await the result,
#   so any async function fits (also one that returns a Future).
# - A coroutine is an Awaitable, but not every Awaitable is a coroutine (a Future is awaitable too).

# Client creation (httpx2)
# - Create ONE AsyncClient in main (`async with`) and bind it with partial(llm_call, client).
#   run_agent never sees the client, only `call`. Reasons: connection reuse, tests can inject a fake,
#   the client's lifetime is visible, and switching provider changes only llm_call.
# - httpx2.AsyncClient and client.post have no `retries` argument (checked, httpx2 2.13.1).
#   `retries` exists on httpx2.AsyncHTTPTransport and only retries connect failures (not read timeouts, not 5xx).
