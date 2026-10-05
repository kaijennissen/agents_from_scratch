# agents_from_scratch

Building a coding agent from scratch. Development happens **inside a container** —
the container is the isolation boundary for the arbitrary code the agent runs —
against an Ollama model server running on the host.

## Develop

Development uses uv with Python 3.14.4; `uv sync` builds the environment. Ollama
on the host is reachable at `$OLLAMA_HOST` (`http://host.docker.internal:11434`).

## Run

```bash
uv run agents-from-scratch -p "what does parse_action do?"
```

Every step of the loop is announced on an event stream — one line per event,
payload indented underneath:

```
        👤 you    what is in src/?
turn  1 🧠 llm    bash · ls -alh src
turn  1 ⚙️ tool   $ ls -alh src
turn  1 📄 tool   ✓ · rc=0 · ms=6
                  total 8
                  drwxr-xr-x  5 kai  staff  160 .
                  -rw-r--r--  1 kai  staff  216 agent.py
turn  2 🧠 llm    exit · src/ has one module, agent.py, which loops over actions.
turn  2 🎯 done   src/ has one module, agent.py, which loops over actions.
turn  2 ⚡ run    2 turns · 2874 tok · 4.1s
```

| | event | |
|---|---|---|
| 👤 | `user.prompt` | the prompt |
| 🧠 | `llm.call` | what the model returned, action wrapper stripped |
| ⚙️ | `tool.call` | the command handed to the shell, as `$ …` |
| 📄 | `tool.result` | return code, duration, output (truncated) |
| 🎯 | `agent.final` | the answer, ending the loop |
| 🧩 | `agent.parse_error` | a reply that contained no action |
| ⚡ | `run.summary` | turns, tokens, wall time |

`-v quiet` prints just the answer, `-v verbose` adds per-call usage and
untruncated output, `-v debug` adds the context size. `--no-color` (or
`NO_COLOR`) for logs.

## Commands

```bash
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pyright          # type-check
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
    /opt/app/bin/agents-from-scratch --prompt "..."

# 4. Review the agent's changes on the host.
git -C /tmp/agent-workspace status
git -C /tmp/agent-workspace diff
```

Omit the trailing command to get an interactive shell in the same
container instead. On a Linux host the clone must be writable by UID 1000,
the container's `agent` user.
