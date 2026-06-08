# Makefile for Planner Subproject

.PHONY: install lint test coverage complexity clean web

install:
	uv sync

lint:
	uv run ruff check .

test:
	uv run pytest

coverage:
	uv run pytest --cov=planner --cov-report=html

complexity:
	uv run radon cc . -a -nc
	uv run radon mi . -n B

web:
	uv run planner web --port 7749

clean:
	rm -rf .pytest_cache .coverage coverage.xml dist build *.egg-info __pycache__ .ruff_cache
