# Development container image.
#
# A Python + uv toolchain for running arbitrary code inside the container
# during development, where the container is the isolation boundary from the
# host. Unlike a deployment image it bakes in NO application code and NO
# dependencies: the source is bind-mounted by the dev container and the project
# plus its dependencies are installed into a venv at container-create time (see
# postCreateCommand in devcontainer.json). Rebuild this image only to change the
# Python or uv version.

FROM python:3.14.4-slim-bookworm

# git: source control and pre-commit run inside the container during dev.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Pinned uv, copied from its published image (matches the host uv version).
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /bin/

# UV_PROJECT_ENVIRONMENT: keep the venv OUTSIDE the bind-mounted workspace so a
#   Linux venv is never written onto the macOS host filesystem (its binaries
#   would be unusable on the host, and bind-mount I/O would slow every install).
# UV_PYTHON_DOWNLOADS=never: use this image's interpreter; fail loudly rather
#   than silently fetch a second Python that disagrees with the base image.
# UV_LINK_MODE=copy: the venv and the uv cache live on different filesystems.
# PATH: make bare `python`, `ruff`, `pytest`, etc. resolve to the project venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

# Non-root development user that owns the venv directory.
RUN useradd --create-home --shell /bin/bash dev \
    && install -d -o dev -g dev /opt/venv

# Keep the venv on PATH in login shells too: Debian's /etc/profile
# unconditionally resets PATH, which would otherwise drop the ENV prepend above
# (so a login-shell `python` would fall back to the base interpreter).
RUN printf 'export PATH="/opt/venv/bin:$PATH"\n' > /etc/profile.d/10-venv.sh

USER dev
