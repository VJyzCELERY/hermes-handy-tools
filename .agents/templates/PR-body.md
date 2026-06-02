## Summary

### Spec / Design References

Resolve paths via: `uv run python .agents/scripts/preflight-pr-body.py --spec <path/to/spec.md> [--design <path/to/design.md>]`
The script outputs repo-root-relative paths (handles worktrees) and can auto-detect `design.md`.

- **Spec**: `<repo-root-relative-path>` — path from repository root to `spec.md`
- **Design**: `<repo-root-relative-path>` — path from repository root to `design.md`

### Problem
[Describe the problem being solved. Reference the spec's problem statement. What was missing, broken, or unclear before this change?]

### Solution
[Describe the solution implemented. Map key changes to spec functional requirements (FR-001, FR-002, etc.). List new modules, modified files, and architectural decisions.]

### Scope

In scope:
- [Map to spec FRs: e.g., FR-001 — user authentication via OAuth]
- [Item 2]

Out of scope:
- [Item 1: explicitly excluded — if from spec, note which FR is deferred]
- [Item 2]

## How to Test

1. Run the test suite:
   ```bash
   cd <subproject-dir> && uv run pytest
   ```
   - Expected: [describe expected test results]

2. Run lint:
   ```bash
   cd <subproject-dir> && uv run ruff check .
   ```
   - Expected: `All checks passed!`

3. Run type checking:
   ```bash
   cd <subproject-dir> && uv run mypy <python_package>/
   ```
   - Expected: Success, no issues.

[Additional verification steps as needed.]

## Review Notes

- [File/module 1] — [what to review closely and why]
- [File/module 2] — [what to review closely and why]

## Related Issues

- [#issue-number](link-to-issue) — [description]
