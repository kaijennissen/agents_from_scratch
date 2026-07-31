FROM python:3.14.4-slim-bookworm

RUN apt-get update -y && \
apt-get install -y curl jq

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/app
WORKDIR /app
COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-install-project

COPY src/ src/

RUN uv sync --locked --no-dev --no-editable 

CMD ["/bin/bash"]

