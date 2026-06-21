.PHONY: setup test lint typecheck dev bench up

setup:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

bench:
	uv run python -m inference_demo.bench.static_vs_continuous

dev:
	uv run uvicorn inference_demo.gateway.app:app --host 127.0.0.1 --port 8000

# Placeholder wired up in phase 7.
up:
	@echo "up: implemented in phase 7 (docker compose)"
