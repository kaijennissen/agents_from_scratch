# agents_from_scratch

Building a coding agent from scratch. Development happens **inside a container** —
the container is the isolation boundary for the arbitrary code the agent runs —
against an Ollama model server running on the host.

## Develop

Open the repo in the dev container (details: [`.devcontainer/README.md`](.devcontainer/README.md)):

- **VS Code**: *Reopen in Container*.
- **Zed**: opens from the same `devcontainer.json`.

The container ships Python 3.14.4 + uv; `uv sync` builds the environment. Ollama
on the host is reachable at `$OLLAMA_HOST` (`http://host.docker.internal:11434`).

## Commands

```bash
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src         # type-check
uv run pytest           # test
```
