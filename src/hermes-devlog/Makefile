.PHONY: test lint

test:
	uv run pytest --cov=hermes_devlog --cov-fail-under=90

lint:
	uv run ruff check .
