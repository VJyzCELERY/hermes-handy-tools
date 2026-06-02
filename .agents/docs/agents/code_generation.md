# Code Generation Rules for AI Agents

## Overview
This document defines the rules and expectations for AI agents generating code for the MAIN-PROJECT and its subprojects.

---

## General Principles
1. **Adopt Coding Standards**:
   - Enforce coding standards as described in `.agents/docs/project_rules/coding_standards.md`.
   - Incorporate logging practices as outlined in `.agents/docs/project_rules/logging_guidelines.md`.
   - Use Ruff auto-fix capabilities to ensure immediate compliance.
   - Include detailed docstrings with descriptions, arguments, and examples for all generated functions and classes.

2. **Purpose-Driven Code**:
   - AI-generated code must have a clear purpose and solve specific tasks or requirements.
   - All code must include comments documenting intent and functionality.

3. **Version Control**:
   - Log changes and generated contributions clearly for traceability.

---

## Commit Naming Rules
AI-generated commits must follow the repository's naming conventions as defined in `../project_rules/commit_naming.md` to ensure consistency in code history.

### Expected Commit Structure
```
type(scope): Commit message

[Optional Body]

[Optional Footer]
```

### Examples
- **Feature Addition**: `feat(auth): implement OAuth2.0 tokens`
- **Bug Fix**: `fix(auth): resolve crash in token refresh`
- **Documentation**: `docs(readme): add API setup guide to README`
- **Bug Fix**: `fix(logging): handle missing log configurations gracefully`
- **Documentation**: `docs(readme): update README with new installation guide`

Ensure commit messages are meaningful, concise, and adhere to the [commit naming rules](../project_rules/commit_naming.md).

---

## Docstring Requirements

All AI-generated functions and classes must use **Google-style docstrings** as defined in `.agents/docs/agents/style.md`. The standard format is:

```python
def function_name(arg1: type, arg2: type) -> ReturnType:
    """Brief description of what the function does.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        Description of the return value.

    Raises:
        ExceptionType: When and why this exception occurs.
    """
```

---

## Exception Handling
- All generated code must include appropriate error handling using `try-except` blocks.
- Clearly define custom exceptions if needed.

---

## Documentation Expectations

### Comprehensive Docs (`docs/full-docs/`)

Whenever code is added, removed, or significantly modified, the corresponding comprehensive documentation **must** be updated in parallel.

**What to update:**
- `docs/full-docs/<subproject>/` — for changes in each subproject (new modules, API changes, removed features)

**Rules:**
- New modules/classes/functions → add documentation to the relevant `.md` file
- Removed features → remove all references from docs (check all affected subproject directories)
- Renamed files → update all doc references and code examples
- Changed behavior → update explanations and code snippets
- Always update `docs/full-docs/INDEX.md` if adding or removing documentation files

**Do not** leave stale references to removed code, deprecated APIs, or renamed files in the comprehensive docs.

---

## Testing Expectations
1. **Test Coverage**:
    - AI-generated code must include corresponding unit and integration tests.
    - Tests must be generated under the appropriate subproject's `tests/` folder.
2. **Documented Test Cases**:
    - Include examples of expected inputs and outputs in the docstrings.