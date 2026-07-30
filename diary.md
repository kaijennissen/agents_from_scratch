# Diary

Append-only log of pitfalls encountered and decisions made while building the agent, newest at the bottom. One entry per topic per day.

30.07.2026 10:09 subprocess(cmd, shell=True), Tags: subprocess, shell, tool; Without `shell=True`, the first argument is the program to run — not a command line.
  - Pass a list: run(["find", ".", "-name", "agent.py"]) → Python executes the program `find` directly with those args. No shell.
  - Pass a string: run("find . -name agent.py") → Python treats the entire string as the program name, so it looks for an executable literally called `find . -name "agent.py" ...` → FileNotFoundError.

  What `shell=True` adds: it runs your string as `/bin/sh -c "your string"`, so a real shell parses it — giving word-splitting, glob expansion (`*.py`), pipes (`|`), `&&`, and redirections like `2>/dev/null` (which the program itself never sees). Caveat: `shell=True` on model-written commands is shell injection by design → the process boundary (container/sandbox), not argv safety, is the real protection.

  `sh -c` contract: the command is the ONE string right after `-c`; tokens after that become positional params ($0, $1, …). So `["/bin/sh","-c"] + shlex.split(cmd)` runs only the first token (`find`) with no args — don't pre-split. And `["/bin/sh","-c", cmd]` is exactly what `shell=True` does internally, so hand-rolling it buys no safety. Decision: use `shell=True` with the raw model string (less code, nothing to hand-add). Safety reasoning: the model authors the whole command, so argv-vs-shell is the wrong layer — real safety is the boundary (non-root container, no secrets reachable, no egress) plus a per-command `timeout`.

30.07.2026 12:21 re.DOTALL, Tags: regex, parsing; Without `re.DOTALL`, `.` matches everything except newlines. In `parse_xml` the pattern `<tag>(.*?)</tag>` needs `re.DOTALL` so that content spanning multiple lines (e.g. a multi-line `<bash>` command) is captured — otherwise the match stops at the first `\n` inside the tag.

30.07.2026 12:21 SYSTEM_PROMPT never sent to model, Tags: system-prompt, messages, bug; Defined `SYSTEM_PROMPT` but never included it in `messages` — the model received only the user's question with no instructions, so it answered generically instead of emitting `<action>` tags. Fix: add `{"role":"system","content":SYSTEM_PROMPT}` as the first element of `messages`. Lesson: defining a prompt ≠ wiring it into the call.

30.07.2026 12:21 `*` can't flatten inside a comprehension, Tags: python, itertools, unpacking; `[*sub for sub in lists]` is a syntax error — `*` unpacks into an enclosing literal or call, not inside a comprehension. To flatten one level of nesting: `itertools.chain.from_iterable(lists)` or a nested comprehension `[x for sub in lists for x in sub]`. Decision: used `itertools.chain.from_iterable` in `parse_action`.

30.07.2026 12:21 2>/dev/null, Tags: shell, redirection; `2` = stderr (fd 2; 0=stdin, 1=stdout), `>` = redirect that stream, `/dev/null` = discard. So `2>/dev/null` throws away error output, keeps stdout. Related: `>/dev/null 2>&1` discards both; `2>&1` merges stderr into stdout (one stream).

30.07.2026 12:21 CompletedProcess not JSON serializable, Tags: subprocess, json, serialization; Appending the raw `subprocess.run(...)` result to `messages` → TypeError because `CompletedProcess` isn't JSON-serializable. Fix: extract `result.stdout`/`result.stderr` (strings) and build `content` from those. Also: without `text=True`, stdout/stderr are `bytes` not `str` → second serialization error waiting to happen.

30.07.2026 12:21 One-action-per-turn (for now), Tags: design, loop, actions; Decision: keep one action per turn. The loop is act→observe→decide — batching bash commands means committing to commands 2–N blind, before seeing command 1's output. Add bash-batching only when a real run shows wasted round-trips on independent commands. `parse_action` already returns lists per kind, so the structure is ready for multiplicity.
