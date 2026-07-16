---
description: Consolidates active PR feedback and posts one replacement review
subtask: true
---

# Review Refresh

Focused entrypoint only; it consolidates posted feedback without owning baseline lifecycle state.

**Query**: `$1` optional PR number/URL.

Read root `AGENTS.md`, skills `review-pr`, `review-core`, and `gh`, plus both common modules and the review template. Set `PR_INPUT=${1:-}`, normalize and acquire it through the review context, then run existing-report preflight from the returned worktree when `$REVIEW_FILE` exists; stale/behind/diverged state blocks remote writes. Fetch active feedback only:

```bash
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --output ./tmp/active-pr-feedback.md
```

Merge active remote and local findings by root issue/location, revalidate applicability, and write one canonical report. Preserve active human discussions. Reply/resolve superseded inline threads and minimize superseded review bodies via `_common-pr-feedback.md`, then execute `review-post.md` and record its returned URLs.

## Required Context

- Root `AGENTS.md`; both common modules; review skills/template; optional local report; `review-post.md`.

## Mutations

- Rewrites canonical local report and replaces stale PR feedback; no Git-history mutation.

## Confirmation

- The explicit `/review-refresh` request authorizes consolidation writes only. Ask before closing active/ambiguous human discussion.

## Failure

- Stop on fetch/validation/interaction/post failure; retain enough local input to retry and never report partial replacement as complete.
