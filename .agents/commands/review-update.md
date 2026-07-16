---
description: Replaces linked PR feedback with the report's current verdict
subtask: true
---

# Review Update

Focused entrypoint only; it replaces posted feedback without owning lifecycle state.

**Query**: `$1` optional report path. **PR**: `$2` optional number/URL.

Read root `AGENTS.md`, skills `review-pr` and `gh`, and both common modules. Normalize the explicit or report-linked PR and acquire it through the review context before deriving the report path or running preflight. Run existing-report preflight from the returned worktree; stale/behind/diverged state blocks remote writes. Preserve active human discussions. Reply before resolving superseded inline links and minimize only actor-owned review bodies. Then execute `review-post.md` and replace local URLs only after success.

## Required Context

- Root `AGENTS.md`; both common modules; skills `review-pr`, `gh`; current linked report; `review-post.md`.

## Mutations

- Replies/resolves/minimizes old PR feedback, posts replacement review, and updates local URLs; no Git-history mutation.

## Confirmation

- The explicit `/review-update` request authorizes this replacement operation only. Ask before touching active human discussion.

## Failure

- Stop on any interaction failure; do not post a replacement until old-link handling is complete, and do not rewrite URLs without successful post output.
