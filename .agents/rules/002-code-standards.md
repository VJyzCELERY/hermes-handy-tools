---
description: Python coding standards, Ruff configuration, absolute imports, naming conventions
globs: "*.py"
alwaysApply: false
---

# Code Standards

## Ruff
- Line length: 88
- Rule set: E, F, I, N, W, D (Google-style docstrings), UP, B, SIM, ARG, LOG, PT, S, PTH, RUF
- Auto-fix on save: `ruff check --fix --select ALL`

## Imports
- Use absolute imports: `from my_package.module import Name`
- Group: stdlib → third-party → local (one line per import, no `*`)

## Naming
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Modules: `short_snake_case`
- Tests: `test_<function>_<scenario>` or `test_gs_<goalspec>_<name>`

## Docstrings
- Google-style: `"""Brief description.\n\nArgs:\n    arg: Description.\n\nReturns:\n    Description.\n"""`

## Complexity
- Max cyclomatic complexity per function: 10 (measured via radon)
- Flag cognitive complexity in review

## Logging
- Use centralized logger: `from my_package.utils.logging import get_logger`
- Log levels: DEBUG (details), INFO (milestones), WARNING (unexpected), ERROR (failures)
- Structured format: `key=value` pairs
