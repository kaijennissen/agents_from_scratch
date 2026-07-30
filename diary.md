# Diary

Append-only log of pitfalls encountered and decisions made while building the agent, newest at the bottom. One entry per topic per day.

30.07.2026 10:09 subprocess(cmd, shell=True), Tags: subprocess, shell, tool; Without `shell=True`, the first argument is the program to run — not a command line.
  - Pass a list: run(["find", ".", "-name", "agent.py"]) → Python executes the program `find` directly with those args. No shell.
  - Pass a string: run("find . -name agent.py") → Python treats the entire string as the program name, so it looks for an executable literally called `find . -name "agent.py" ...` → FileNotFoundError.

  What `shell=True` adds: it runs your string as `/bin/sh -c "your string"`, so a real shell parses it — giving word-splitting, glob expansion (`*.py`), pipes (`|`), `&&`, and redirections like `2>/dev/null` (which the program itself never sees). Caveat: `shell=True` on model-written commands is shell injection by design → the process boundary (container/sandbox), not argv safety, is the real protection.

  `sh -c` contract: the command is the ONE string right after `-c`; tokens after that become positional params ($0, $1, …). So `["/bin/sh","-c"] + shlex.split(cmd)` runs only the first token (`find`) with no args — don't pre-split. And `["/bin/sh","-c", cmd]` is exactly what `shell=True` does internally, so hand-rolling it buys no safety. Decision: use `shell=True` with the raw model string (less code, nothing to hand-add). Safety reasoning: the model authors the whole command, so argv-vs-shell is the wrong layer — real safety is the boundary (non-root container, no secrets reachable, no egress) plus a per-command `timeout`.
