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


### Run the agent

The agent runs in a hardened container. It can edit an independent clone of
this repository mounted at `/workspace`; the code driving the run is the
read-only copy baked into the image at `/app`. Only committed work reaches the
clone.

```sh
# 1. Build the image with the current harness.
docker build --tag agent_sandbox --file Dockerfile .

# 2. Create a fresh, independent clone for the agent to work in.
rm -rf /tmp/agent-workspace
git clone --no-hardlinks . /tmp/agent-workspace

# 3. Run one agent invocation against the clone.
docker run --rm \
    -it \
    --read-only \
    --tmpfs /tmp:size=64m \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 100 \
    --memory 4g \
    --cpus 2 \
    --add-host=host.docker.internal:host-gateway \
    --volume /tmp/agent-workspace:/workspace \
    --name agent-sandbox \
    agent_sandbox \
    /opt/app/bin/python /app/src/agent.py --prompt "..."

# 4. Review the agent's changes on the host.
git -C /tmp/agent-workspace status
git -C /tmp/agent-workspace diff
```

Omit the trailing `python` command to get an interactive shell in the same
container instead. On a Linux host the clone must be writable by UID 1000,
the container's `agent` user.
