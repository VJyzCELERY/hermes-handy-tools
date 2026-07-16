---
description: Posts the canonical report as one PR review and records URLs
subtask: true
---

# Review Post

Focused entrypoint only; it posts an already validated canonical report.

**Query**: `$1` optional report path. **PR**: `$2` optional number/URL.

Read root `AGENTS.md`, skills `review-pr` and `gh`, both common modules, and the three review-post templates. Normalize the explicit or report-linked PR and acquire it through the review context before deriving the report path or running preflight. Run existing-report preflight from the returned worktree; stale/behind/diverged state blocks posting. Fetch metadata as JSON and the diff as raw text:

```bash
uv run python .agents/scripts/gh.py fetch pr "$PR_NUMBER" --json number,baseRefName,headRefName,headRefOid --format json
uv run python .agents/scripts/gh.py cmd --format raw pr diff "$PR_NUMBER"
```

Build `./tmp/review-body.md` and a valid JSON array at `./tmp/review-comments.json`. Include every finding in the body; create inline comments only for OPEN locations present on the current diff. Map Approved states to `APPROVE`, Change Requested/Blocked to `REQUEST_CHANGES`, otherwise `COMMENT`. Post using `_common-pr-feedback.md`, check output, and record the returned review/comment URLs in `$REVIEW_FILE`.

## Required Context

- Root `AGENTS.md`; both common modules; skills `review-pr`, `gh`; posting templates; current canonical report.

## Mutations

- Posts one PR review and updates local URL fields; no Git-history mutation.

## Confirmation

- The explicit `/review-post` request authorizes this review post only. Fresh permission before any commit, squash, or push.

## Failure

- Stop before posting on stale data, invalid JSON, unmappable required lines, or empty body. On post failure, do not add URLs.
