# Code Style

## Language and Runtime

- **Python 3.11+** is the minimum supported version
- **uv** is used for dependency and virtualenv management
- **Ruff** is used for all linting and formatting enforcement

---

## Formatting Rules

- **Line length**: 120 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: double quotes for strings
- **Imports**: absolute imports only — relative imports are banned (Ruff `TID252`)

---

## Naming Conventions

| Scope | Convention | Example |
|-------|-----------|---------|
| Modules / files | `snake_case` | `user_service.py` |
| Classes | `PascalCase` | `UserService` |
| Functions / methods | `snake_case` | `get_user_by_id` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Private members | `_leading_underscore` | `_internal_helper` |
| Async coroutines | suffix with `_async` | `fetch_data_async` |

See `.agents/docs/project_rules/naming_conventions.md` for the full naming rules including subproject and source folder conventions.

---

## Docstrings

Use **Google-style docstrings** for all public functions, classes, and modules.

```python
def process_order(order_id: str, amount: float) -> dict:
    """Process a payment order and return the transaction result.

    Args:
        order_id: Unique identifier for the order.
        amount: Amount to charge in the account currency.

    Returns:
        A dict containing transaction_id, status, and timestamp.

    Raises:
        ValueError: If amount is negative or order_id is empty.

    Example:
        result = process_order("ord_123", 49.99)
        print(result["status"])  # "success"
    """
```

Tests may omit docstrings but must follow `test_<behavior>` naming (e.g., `test_returns_none_when_id_missing`).

---

## Ruff Configuration

Ruff is configured per subproject in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "D", "C901"]
fixable = ["ALL"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]  # skip docstring rules in tests

[tool.ruff.lint.mccabe]
max-complexity = 15
```

---

## Pre-commit Iteration

Run `make lint` repeatedly until all checks pass:

1. First run: Ruff may auto-fix formatting and import order
2. Second run: Verify no remaining violations
3. If violations remain after auto-fix: manually fix them

```bash
make lint    # fix + check
make lint    # verify clean
```

---

## What to Avoid

- `print()` statements in non-CLI code — use `logging` instead (see `.agents/docs/project_rules/logging_guidelines.md`)
- Relative imports — always use absolute imports
- Wildcard imports (`from module import *`)
- Mutable default arguments (`def foo(items=[])`)
- Bare `except:` clauses — always catch specific exception types

---

## References

- `.agents/docs/project_rules/coding_standards.md` — full coding standards
- `.agents/docs/project_rules/naming_conventions.md` — naming rules
- `.agents/docs/project_rules/logging_guidelines.md` — logging rules
- `.agents/docs/project_rules/cognitive_complexity.md` — complexity limits
