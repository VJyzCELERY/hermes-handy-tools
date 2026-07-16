---
description: Logs and archives a completed clean review cycle
subtask: true
---

# Review Archive

**Query**: `$1` optional explicit review path.

Read root `AGENTS.md`, skill `review-core`, and `_common-review-context.md`. Run the existing-report preflight. Refuse stale, behind/diverged, malformed, or OPEN reports. Finalize through the shared workflow, then validate the log:

```bash
uv run python .agents/scripts/review_workflow.py finalize "$REVIEW_FILE" --archive-dir ./reviews/archives
uv run python .agents/scripts/review-log.py --validate "./reviews/log/REVIEW_${REPORT_NORMALIZED_BRANCH}.md"
```

## Required Context

- Root `AGENTS.md`; `_common-review-context.md`; skill `review-core`; completed canonical report.

## Mutations

- Appends local review log and moves the local report to archives; no Git-history or remote mutation.

## Confirmation

- None for a valid completed report. No commit, squash, or push is permitted.

## Failure

- Stop before moving when the report HEAD is stale or logging fails. If move/validation fails, report exact paths and do not fabricate success.
