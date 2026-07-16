---
description: Clarifies and verifies review findings against current local state
subtask: true
---

# Review Validate

**Query**: `$1` optional review path/focus. **Findings**: `$2` optional IDs/severity.

Read root `AGENTS.md`, rule `004-review-standards.md`, skill `review-core`, and `_common-review-context.md`. Do not load the baseline orchestration command. Run `uv run python .agents/scripts/preflight-review.py --validate --review-file "$REVIEW_FILE"`; staleness is allowed, but behind/diverged state is not. For each selected OPEN finding, clarify every canonical field without changing intent, run its validation against current local and unstaged content, and set ADDRESSED when fixed, INVALID when demonstrably inapplicable, otherwise OPEN. Refresh the commit range with `update-commit-range.py`, save, and return all status counts with evidence.

## Required Context

- Root `AGENTS.md`; `_common-review-context.md`; review skill/rule; canonical report and log.

## Mutations

- Updates the local review report; no source, Git-history, or remote mutation.

## Confirmation

- None unless the filter is ambiguous.

## Failure

- Stop when either phase fails; do not claim validation or continue to fixes without executable evidence.
