.DEFAULT_GOAL := help

.PHONY: help
help:  ## this help section
	@awk 'BEGIN {FS = ":.*##"; printf "\nusage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: lint
lint:  ## ruff lint checks
	uv run ruff check .

.PHONY: format
format:  ## ruff auto-format
	uv run ruff format .

.PHONY: typecheck
typecheck:  ## mypy static type checks
	uv run mypy src

.PHONY: test
test:  ## run the test suite
	uv run pytest
