---
date: 2026-07-30
author: Kai Jennissen
topic: Hardened container for the coding agent
tags: [agent, docker, isolation, security]
status: accepted
---

# Hardened agent-container design

## Overview

The coding agent executes model-written shell commands. Those commands are
untrusted even when the model and prompt are local: a mistaken command can
delete files, exhaust host resources, read credentials, or send repository
contents over the network.

The agent therefore runs entirely inside a purpose-built Docker container. The
container receives an isolated copy of the repository, not the developer's real
working tree. It may change that copy freely. The developer reviews the changes
on the host and is the only party that commits or publishes them.

This document records the accepted design. The hardened runtime described here
is not yet implemented.

## Current state

`src/agent.py` calls Ollama and executes the returned command through a shell.
The repository's dev container provides a consistent development environment,
but it bind-mounts the real repository for editing. It is not the security
boundary for model-written commands.

## End state

```text
Host
├── real repository (never mounted into the agent container)
├── Ollama
└── /tmp/agent-workspace (independent clone)
          │
          │ writable bind mount
          ▼
Hardened container
├── immutable src/agent.py from the image
├── read-only root filesystem
├── disposable /tmp
└── /workspace (agent may read, write, and delete)
```

One container runs one complete agent invocation. The running copy of
`src/agent.py` comes from the image. `/workspace` contains a separate copy of
the repository. This remains true while dogfooding: if the agent edits
`/workspace/src/agent.py`, it changes the review copy, not the process that is
driving the active run.

## Decisions

### Run the whole agent inside one purpose-built container

Python, `src/agent.py`, its dependencies, and every model-written shell command
run inside the same container. The container is created for one invocation and
removed afterward.

This keeps the first implementation small: there is no host-side orchestrator
and no separate command-execution service. A Docker container shares the Docker
host's Linux kernel, so this does not claim the stronger isolation of a
dedicated virtual machine.

The development container remains a developer tool. It is not used to run
untrusted commands because it intentionally exposes the real working tree.

### Bake the harness into the image

The image copies `src/agent.py` and installs its locked Python dependencies at
build time. The image copy is immutable during a run. Runtime input is limited
to the user's prompt, the isolated workspace, and access to Ollama.

The agent does not receive the host's environment wholesale. No SSH agent,
GitHub credential, cloud credential, Docker socket, or user home directory is
mounted into the container.

### Give the agent an independent writable clone

Before each run, the host creates a fresh local clone outside the real
repository, for example at `/tmp/agent-workspace`. The clone is bind-mounted
read-write at `/workspace`.

The clone uses `git clone --no-hardlinks`. A local clone may otherwise hard-link
Git object files to the source repository. Explicitly copying the objects keeps
the clone independent even if a command writes directly into `.git/objects`.

A Git worktree is not used. A worktree shares the source repository's Git
object database and refs, so making it usable inside the container would expose
the real repository metadata. The real working tree is not mounted read-write
or read-only; the clone is the complete workspace.

### Keep review, commits, and publishing on the host

The agent changes files only. It does not commit, push, or open pull requests.
Git and repository credentials are therefore not required in the runtime
image.

After the container exits, the developer reviews the isolated clone:

```bash
git -C /tmp/agent-workspace status
git -C /tmp/agent-workspace diff
```

If the changes are accepted, the developer creates a branch and commit in that
clone. The real repository can fetch the branch directly from the clone:

```bash
git -C /tmp/agent-workspace switch -c agent-run
git -C /tmp/agent-workspace add <approved-paths>
git -C /tmp/agent-workspace commit -m "Describe the accepted change"

# Run from the real repository.
git fetch /tmp/agent-workspace agent-run
git diff main...FETCH_HEAD
git switch -c agent-run FETCH_HEAD
```

Fetching from a filesystem path uses the same Git mechanism as fetching from
`origin`. `origin` is only a saved name for a repository location. An explicit
path needs no configured remote and no network access; the fetched branch is
available through `FETCH_HEAD` until it is given a local branch name.

### Harden the container in layers

The security contract is that model-written commands can change the isolated
workspace and bounded temporary storage but cannot persist writes elsewhere,
gain additional privileges, access host credentials, control Docker, or
consume unbounded resources.

The runtime applies these controls:

| Control | Meaning |
|---|---|
| Non-root user | Commands do not start with administrator privileges inside the container. |
| Read-only root filesystem | Files baked into the image cannot be changed during a run. |
| Temporary `/tmp` | Programs get bounded scratch space that disappears with the container. |
| Drop Linux capabilities | Remove special kernel permissions that ordinary code does not need. |
| No new privileges | A child process cannot gain privileges through set-user-ID programs. |
| Default seccomp policy | Docker continues blocking selected dangerous system calls. |
| Process, memory, and CPU limits | Fork bombs and runaway programs cannot consume the whole Docker host. |
| Per-command timeout | A command that hangs is terminated by the agent loop. |
| No Docker socket | The agent cannot create privileged containers or control other containers. |
| Ephemeral container | Container-local changes disappear after each invocation. |

The initial resource limits are one CPU, 512 MiB of memory, 256 processes, a
64 MiB `/tmp`, and 30 seconds per shell command. These are operational defaults,
not security invariants; they may be tuned when real tasks show that they are
too small or too large.

### Reach host Ollama and state the egress limitation honestly

The container reaches Ollama through `host.docker.internal`. The runtime also
adds Docker's portable host-gateway mapping so the same name works when the
Docker daemon does not provide it automatically.

This network path also permits general outbound traffic. The first runtime does
not claim deny-by-default egress. This is an accepted limitation for local
dogfooding with a local model, no runtime secrets, and non-sensitive learning
work.

If the agent later handles untrusted input, sensitive repositories, or cloud
credentials, Ollama moves into its own container. Both containers then join a
Docker network created with external routing disabled. They can communicate
with each other while the agent has no route to the internet. That trigger
closes the limitation without adding host firewall rules or a custom proxy.

### Keep temporary storage separate from shared work

`/tmp` is a memory-backed temporary filesystem. It is private to the container
and disappears when the container stops. It is used only for disposable
scratch data.

The workspace is a bind mount because the host must review it after the
container exits. A temporary filesystem cannot provide that handoff: commits
and files stored only there would be lost unless a separate export mechanism
ran before shutdown.

### Make the supported command visible

The long, security-sensitive container invocation belongs in one Make target so
developers do not need to reconstruct its flags by memory. The README explains
the trust boundary, each Linux-oriented hardening control in plain language,
the accepted network limitation, and the clone-review-import workflow.

The Make target and README must describe the same command. A flag present only
in prose is not an enforced protection.

## Alternatives not chosen

- **Docker Sandboxes:** stronger microVM and network isolation, but hides the
  mechanisms this learning project is intended to explore and complicates
  access to host Ollama.
- **The dev container as the runtime boundary:** it exposes the real working
  tree by design.
- **Mounting the real repository read-write:** lets an untrusted command damage
  the developer's work directly.
- **Mounting the real repository read-only:** prevents damage but also prevents
  the agent from doing useful coding work.
- **A Git worktree:** shares the real repository's Git metadata.
- **A temporary-filesystem workspace:** requires a second export mechanism and
  loses all work if the run ends before export.
- **GitHub from inside the container:** requires network egress and credentials
  inside the untrusted execution boundary.

## Resulting boundary

The agent is trusted to modify one independent repository clone. It is not
trusted with the real repository, GitHub credentials, the host environment, the
Docker daemon, or unrestricted host resources. Internet egress remains an
explicitly accepted limitation while Ollama runs on the host.
