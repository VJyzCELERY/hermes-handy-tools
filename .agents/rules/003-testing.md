---
description: Python pytest organization, behavior coverage, and coverage target
globs: "*.py, pyproject.toml"
alwaysApply: false
---

# Python Testing Standards

- Use pytest and pytest-cov; use pytest-asyncio only for asynchronous behavior.
- Write the failing test before implementation and confirm that it fails for the expected reason.
- Keep application tests under each Python subproject's `tests/`; repository-owned agent script tests live under `.agents/scripts/tests/` and run from the repository root.
- Name files `test_<module>.py` and tests `test_<behavior>_<scenario>` or `test_gs_<goalspec>_<name>`.
- Test observable public behavior, including success, error, edge, and trust-boundary validation paths. Do not test private helpers directly.
- Use fixtures for genuinely shared setup and parametrization for the same behavior over multiple cases.
- Target at least 90% coverage for new code. Coverage supports, but never replaces, behavior-focused assertions.
- Run tests from the Python subproject root with `uv run`; never use bare `pytest`.
