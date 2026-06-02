Standard status definitions and validation flow for review findings.

### Status definitions
- **OPEN**: Issue exists and needs attention
- **ADDRESSED**: Issue has been fixed (validation passes)
- **INVALID**: No longer relevant — stale or outside current scope
- **DEFERRED**: Valid issue but deferred to a future cycle

### Validation priority
1. Critical → High → Medium → Low (fix highest severity first)
2. Always run the "How to Validate" command to determine status
3. Use `uv run` prefix for all Python validation commands
4. Document evidence from command output

### Common flow
1. Read the review report
2. For each OPEN finding: run validation → determine status → update
3. If finding has PR Comment URL: post reply with result
4. ADDRESSED/INVALID → reply + resolve. OPEN → reply (no resolve)
