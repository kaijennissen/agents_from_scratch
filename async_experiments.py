import asyncio
import os
import signal
from dataclasses import dataclass
from typing import Self

TIMEOUT = 2


@dataclass(frozen=True)
class BashResult:
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool

    @classmethod
    def completed(cls, stdout: str, stderr: str, returncode: int) -> Self:
        return cls(stdout, stderr, returncode, timed_out=False)

    @classmethod
    def timeout(cls, stdout: str = "", stderr: str = "") -> Self:
        return cls(stdout, stderr, returncode=None, timed_out=True)


def format_observation(cmd: str, result: BashResult) -> str:
    """Turn a BashResult into the text the model reads."""
    if result.timed_out:
        return (
            f"Command `{cmd}` was killed after a timeout of {TIMEOUT} seconds. "
            "It did not finish, so its result and side effects are unknown, "
            "and any output it produced was discarded."
        )
    return (
        f"Command `{cmd}` finished with exit code {result.returncode}.\n"
        f'stdout: "{result.stdout}"\n'
        f'stderr: "{result.stderr}"'
    )


async def run(cmd):
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
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            returncode=proc.returncode,
        )

    except TimeoutError:
        return BashResult.timeout()

    finally:
        try:
            os.killpg(proc_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


async def main():
    cmds = ["for i in 1 2 3 4 5;do echo $i; sleep $i; done", "ls -alh", "ls -alh priv"]
    results = await asyncio.gather(*(run(c) for c in cmds))
    for cmd, result in zip(cmds, results, strict=False):
        print(format_observation(cmd, result), end="\n\n")


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
