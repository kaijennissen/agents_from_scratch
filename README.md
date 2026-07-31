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


### Docker
```sh
docker build --tag agent_sandbox --file Dockerfile .
docker run  --rm \
    -it \
    --read-only \
    --tmpfs /tmp:size=64m \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 100 \
    --memory 4g \
    --cpus 2 \
    --add-host=host.docker.internal:host-gateway \
    --name agent-sandbox \
    agent_sandbox

# add later once added to Dockerfile    
\\#--user 1000:1000 \
#--volumne /tmp/agent-workspace:/workspace \
```
