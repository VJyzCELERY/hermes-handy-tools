# Makefile for Python Subproject

.PHONY: install lint test coverage complexity clean

# Install dependencies
install:
	uv sync

# Run linter (Ruff)
lint:
	uv run ruff check .

# Run tests
test:
	uv run pytest

# Run tests with coverage
coverage:
	uv run pytest --cov=sub_project --cov-report=html

# Run cognitive complexity analysis (radon)
complexity:
	uv run radon cc . -a -nc
	uv run radon mi . -n B

# Clean up artifacts
clean:
	rm -rf .pytest_cache .coverage coverage.xml dist build *.egg-info __pycache__ .ruff_cache
