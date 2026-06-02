---
description: Review standards, severity levels, security considerations
globs: "*.md, *.py"
alwaysApply: false
---

# Review Standards

## Severity Levels
- **CRITICAL**: Security vulnerability, data loss, spec violation, test breakage
- **HIGH**: Incorrect behavior, missing validation, poor error handling
- **MEDIUM**: Code quality, documentation gaps, maintainability
- **LOW**: Style nits, minor suggestions

## Review Focus Areas
- **Correctness**: Does the code do what the spec says?
- **Security**: Input validation, auth, data exposure, dependency risks
- **Performance**: Unnecessary allocations, N+1 queries, caching
- **Maintainability**: Complexity, naming, duplication, test coverage
- **Documentation**: Docstrings, README, API docs updated?

## Finding Format
Each finding must include: file:line, severity, description, why it matters, suggested fix, and a validation command prefixed with `uv run`.

## Security Checklist
- No hardcoded secrets, credentials, or API keys
- Input validation at all boundaries
- Authentication and authorization checks
- Safe from injection attacks (SQL, command, path)
- Sensitive data not exposed in logs or error messages

## Review Flow
1. Unbiased review (no log context) → find issues
2. Cross-reference against review log (previously addressed/deferred)
3. Clarify vague findings → verify each one → update statuses
4. Only ADDRESSED, INVALID, or DEFERRED statuses allowed in log
