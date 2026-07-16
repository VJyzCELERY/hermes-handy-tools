---
description: Fetches and merges PR feedback into the canonical local report
subtask: true
---

# Review Fetch

**Query**: `$1` optional PR number/URL.

Read root `AGENTS.md`, skills `review-pr` and `gh`, `_common-review-context.md`, `_common-pr-feedback.md`, and the review template. Set `PR_INPUT=${1:-}`, normalize it with `preflight-pr.py` (omit the positional argument when empty), and acquire it through the review context before deriving report paths. Fetch all feedback from the returned worktree for reconciliation:

```bash
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --all --output "./reviews/remote/REVIEW_${NORMALIZED_BRANCH}_fetched.md"
```

Merge into `$REVIEW_FILE`, preserving unique local context and remote URLs. Deduplicate by root issue/location; remote-linked findings outrank unlinked duplicates. Before resolving/minimizing older duplicate links, verify the newer authoritative link and preserve active human discussion. Refresh report metadata from `fetch pr --format json`.

## Required Context

- Root `AGENTS.md`; both common modules; skills `review-pr`, `gh`; review template; optional existing report.

## Mutations

- Local remote/canonical review files only. Remote cleanup belongs to `/review --sync-remote`.

## Confirmation

- None for requested fetch/merge; this entrypoint never closes remote links.

## Failure

- Stop on PR normalization/fetch/parse/write/remote failure; preserve the existing canonical report unchanged when merge cannot complete.
