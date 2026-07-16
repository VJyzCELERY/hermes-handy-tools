---
description: Python coding, naming, logging, and complexity standards
globs: "*.py, pyproject.toml"
alwaysApply: false
---

# Python Code Standards

## Tooling

- Ruff line length: 88.
- Ruff rule families: E, F, I, N, W, D with Google-style docstrings, UP, B, SIM, ARG, LOG, PT, S, PTH, and RUF.
- Maximum cyclomatic complexity per function: 10, measured by Ruff C901 or radon.
- Run formatting and safe fixes through the subproject's configured Ruff commands; inspect changes before accepting them.

## Imports And Naming

- Use absolute imports, ordered stdlib, third-party, then local. Never use wildcard imports.
- Classes use `PascalCase`; functions and variables use `snake_case`; constants use `UPPER_SNAKE_CASE`; private names use a leading underscore.
- Modules use short `snake_case` names.
- Public modules, classes, and functions use concise Google-style docstrings.

## Python Practices

- Use the standard `logging` module unless the subproject already defines a logger utility. Do not invent a project-wide package path.
- Use `DEBUG` for diagnostics, `INFO` for milestones, `WARNING` for recoverable unexpected states, and `ERROR` for failures.
- Prefer structured `key=value` context and never log secrets or sensitive personal data.
- Avoid mutable default arguments, bare `except`, and `print()` outside CLI output or tests.
