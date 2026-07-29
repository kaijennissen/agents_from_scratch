# Dev container

Develop inside a container so the container — not your host — is the isolation
boundary for the arbitrary code this project runs. Your editor's terminal,
language server, tests, and Python interpreter all run inside the container
against the bind-mounted source.

## Open it

- **VS Code**: install the *Dev Containers* extension, then
  *Reopen in Container* (bottom-left menu, or the command palette).
- **Zed**: opens the container from the same `devcontainer.json`.

Either way, the first launch builds the image and runs `uv sync --frozen`.

## What you get

- Python **3.14.4** and **uv** (pinned), plus `git`.
- No application code or dependencies are baked into the image. The source is
  bind-mounted, and `uv sync --frozen` installs the dependencies plus an
  editable install of the project into a venv at **`/opt/venv`**, so edits to
  the source take effect immediately.
- `python`, `ruff`, `pytest`, etc. resolve to that venv automatically (it is on
  `PATH`). You can also use `uv run <cmd>`.

## Talking to Ollama on your host

`ollama serve` runs on your **host** (default `127.0.0.1:11434`). Inside the
container it is reachable at `host.docker.internal:11434`, exposed as the
`OLLAMA_HOST` environment variable:

```python
import os, httpx
httpx.get(f"{os.environ['OLLAMA_HOST']}/api/version").json()
```

Make sure Ollama is running on the host first.

## Notes

- The venv lives at `/opt/venv`, **not** `.venv` in the repo. That keeps the
  Linux venv off the macOS host filesystem (its binaries would be unusable
  there) and off the slow bind mount. After changing dependencies, rerun
  `uv sync` to rebuild it.
- To run git hooks inside the container: `uv run pre-commit install` (once).
- Rebuild the image only to change the Python or uv version; day-to-day
  dependency changes are just `uv sync`.
