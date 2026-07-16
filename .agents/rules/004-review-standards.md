---
description: Review standards, severity levels, security considerations
globs: "*.md, *.py"
alwaysApply: false
---

# Review Standards

## Severity Levels
- **CRITICAL**: Causes or enables irreversible data loss, broad security compromise, or a release-wide outage.
- **HIGH**: Breaks a primary workflow, exposes sensitive data, or causes substantial incorrect behavior for many users.
- **MEDIUM**: Breaks a secondary workflow or creates a concrete reliability, performance, accessibility, or maintainability risk.
- **LOW**: Has limited impact and a practical improvement; style preferences without behavioral impact are not findings.

## Review Focus Areas
- **Correctness**: Does the code do what the spec says?
- **Security**: Input validation, auth, data exposure, dependency risks
- **Performance**: Unnecessary allocations, N+1 queries, caching
- **Maintainability**: Complexity, naming, duplication, test coverage
- **Documentation**: Docstrings, README, API docs updated?
- **Scope discipline**: Is this the simplest sufficient change, without speculative abstractions, dependencies, optimization, or configuration?
- **Debt and stubs**: Are production stubs absent or adjacent to a valid explained debt marker? Are debt IDs well formed, intentional shared IDs semantically related, and mandatory safeguards never deferred as debt?

Valid, scoped debt is not automatically a finding. Report malformed, vague, stale, unsafe, or unrelated shared debt markers and every unrecorded production stub.

## Finding Format
Use one schema for reports, review bodies, inline comments, and logs:

- Heading: `### [CATEGORY-SUBJECT-NNN] - [SEVERITY] - Short title`.
- IDs are uppercase, use exactly three digits, and remain stable across review cycles. `CATEGORY` matches the required `Category` field; `SUBJECT` names the affected concern.
- Status is exactly `OPEN`, `ADDRESSED`, `INVALID`, or `DEFERRED`.
- Severity is exactly `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` and is based on impact above, not effort.
- Every finding requires `Status`, `Severity`, `Category`, `Location`, `Description`, `Why It Matters`, `Suggested Fix`, `How to Validate`, and `Expected Addressed Result`.
- `Location` is a repository-relative `file:line` when possible; use a precise component only when no line applies.
- `How to Validate` contains a runnable command in a `bash` fence. Python commands use `uv run`; non-Python commands need not. The command must return nonzero on failure or produce exact output/state described by `Expected Addressed Result`.
- A clean report contains `No findings.` under `## Findings`; any other unstructured or malformed finding content is invalid.

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
4. Reports allow all four statuses; archival logs allow only ADDRESSED, INVALID, or DEFERRED
