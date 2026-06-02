# Testing Configuration Reference

This file documents the **pytest configuration and coverage setup** for subprojects. For the developer testing **workflow and conventions**, see `.agents/docs/agents/testing.md`.

Testing is managed using `pytest` across the MAIN-PROJECT and its subprojects, with mandatory test organization and coverage standards.

---

## Test Organization
- **Unit Tests**:
  - Small, isolated tests for components.
  - Store in `tests/unit/`.
- **Integration Tests**:
  - Broader tests for system-level interactions.
  - Store in `tests/integration/`.

---

## Pytest Configuration
The following configuration must be included in subproject `pyproject.toml` files:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers --disable-warnings --maxfail=2"
```

### Example Test Structure
Below is an example of how to structure your `unit` and `integration` tests:

#### Unit Test Example
```python
# tests/unit/test_math_operations.py
import pytest

# Function to be tested
def addition(a, b):
    return a + b

def test_addition():
    assert addition(2, 3) == 5

@pytest.mark.parametrize("a, b, expected", [
    (1, 1, 2),
    (2, 3, 5),
    (-1, 1, 0)
])
def test_addition_param(a, b, expected):
    assert addition(a, b) == expected
```

#### Integration Test Example
```python
# tests/integration/test_end_to_end.py
from my_app import run_app

def test_app_runs():
    result = run_app()
    assert result == "Success"
```

---

## Test Coverage
1. **Coverage Goals**:
   - Achieve at least 80% coverage for all subprojects.
2. **Tools**:
   - Use `pytest-cov` for measuring coverage.
   - Example command:
     ```bash
     uv run pytest --cov=src --cov-report=html
     ```