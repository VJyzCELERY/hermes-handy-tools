---
description: Test framework, naming, organization, and coverage expectations
globs: "*.py"
alwaysApply: false
---

# Testing Standards

## Framework
- pytest with pytest-cov, pytest-asyncio
- Tests live in `tests/` under each subproject

## Organization
- Unit tests: `tests/unit/` or `tests/test_<module>.py`
- Integration tests: `tests/integration/`
- Test modules mirror source package structure

## Naming
- Functions: `test_<function>_<scenario>` or `test_gs_<goalspec>_<name>`
- Files: `test_<module>.py`
- Classes: `Test<Feature>`

## Structure
- Arrange-Act-Assert (AAA)
- Fixtures for shared setup (conftest.py)
- Parametrize for multiple scenarios: `@pytest.mark.parametrize`
- Async tests: `async def test_...` with pytest-asyncio

## Coverage
- 90%+ target for new code
- Coverage is a side effect, not the goal — test behavior, not lines

## What to Test
- Success paths + error cases + edge cases
- Public API only (not private helpers)
- Integration tests for workflows spanning multiple modules
