# Testing Guidelines (Developer Workflow)

For pytest configuration and coverage setup, see `.agents/docs/project_rules/testing_guidelines.md`.

---

## Test Directory Structure

Each subproject must follow this structure:

```
src/my-subproject/
└── tests/
    ├── unit/
    │   └── test_<module>.py
    └── integration/
        └── test_<feature-name>.py
```

- **Unit tests** (`tests/unit/`): test individual functions and classes in isolation
- **Integration tests** (`tests/integration/`): test workflows, API interactions, and cross-module behavior

---

## Naming Conventions

- Test files: `test_<topic>.py` (e.g., `test_user_service.py`, `test_auth_flow.py`)
- Test functions: `test_<behavior>` — describe what the test verifies, not the method name

**Good names:**
```python
def test_returns_none_when_user_id_is_missing():
def test_raises_value_error_on_negative_amount():
def test_creates_order_and_sends_confirmation_email():
```

**Bad names:**
```python
def test_get_user():       # what does it test about get_user?
def test_1():              # meaningless
def testGetUser():         # wrong casing
```

---

## Writing Tests

### Use pytest Fixtures

Define reusable fixtures in `conftest.py` at the test root or subproject root:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_user():
    return {"id": "usr_001", "email": "test@example.com", "active": True}
```

### Test-First Workflow

1. Write the failing test first
2. Run `make test` — confirm it fails with the expected error
3. Write the minimum implementation to make it pass
4. Run `make test` — confirm it passes
5. Refactor if needed, keeping tests green

### Test Coverage Requirements

- Minimum **80% coverage** enforced via `pytest-cov`
- Check coverage: `make coverage`
- Coverage report is generated in `htmlcov/` (excluded from git)

---

## Test Module Focus

Keep test modules focused. If a single test file grows to hundreds of lines covering unrelated behaviors, split it into feature-oriented modules:

```
tests/unit/
├── test_user_creation.py
├── test_user_authentication.py
└── test_user_permissions.py
```

Rather than one large `test_user.py` covering everything.

---

## Edge Cases to Always Cover

- `None` / `null` inputs
- Empty strings, lists, and dicts
- Boundary values (0, -1, max int)
- Invalid types passed to typed functions
- Error paths: exceptions, failures, timeouts

---

## What to Avoid

- Tests that only test implementation details (test behavior, not internals)
- Tests with multiple unrelated assertions — one behavior per test
- Hardcoded file paths or absolute paths in tests — use `tmp_path` fixture
- `time.sleep()` in tests — use mocks for time-dependent code
- Skipping tests with `@pytest.mark.skip` without a documented reason

---

## Running Tests

```bash
# From a subproject directory
make test          # run all tests
make coverage      # run with coverage report

# Directly with pytest (must use uv run)
cd src/<subproject-dir> && uv run pytest tests/unit/ -v
cd src/<subproject-dir> && uv run pytest tests/integration/ -v
cd src/<subproject-dir> && uv run pytest tests/ -k "test_returns_none"

# ❌ WRONG - bare pytest may import from wrong worktree
# pytest tests/unit/ -v
```

---

## References

- `.agents/docs/project_rules/testing_guidelines.md` — full testing rules
- `.agents/docs/agents/workflow.md` — full development commands
