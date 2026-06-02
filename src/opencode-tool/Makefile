.PHONY: install test lint format clean

install:
	pip install -e .

test:
	python -m pytest

lint:
	python -m ruff check .

format:
	python -m ruff format .

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
