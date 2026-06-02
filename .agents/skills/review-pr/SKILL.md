---
name: review-pr
description: Post reviews via review-post, update via review-update, refresh via review-refresh
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: review-pr — PR Review Operations

## Purpose

Manage the full review lifecycle: post reviews, update after fixes, consolidate all reviews. All posting goes through `review-post` which uses `.agents/templates/` for consistent formatting.

## Prerequisites

- Load skill: preflight (for preflight-pr.py)
- Load skill: gh (for gh.py — all posting/fetching/interact operations)

## Execution

### Post a review (review-post)
1. Detect PR: `PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)`
2. Get PR diff via `uv run python .agents/scripts/gh.py cmd pr diff "$PR_NUMBER"`
3. Read Overall Assessment from report header → determines review event + emote
4. Read `.agents/templates/review-body-snippet.md` and `.agents/templates/inline-comment-format.json` for structure
5. Read `.agents/templates/inline-comment-body-snippet.md` for inline comment body format
6. Build inline comments JSON in `./tmp/` using the templates
7. Post a single review with all inline comments + body: `uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/body.md ./tmp/comments.json --event "$EVENT"`
   - The review body (from `.agents/templates/review-body-snippet.md`) lists ALL findings — inline findings marked "Details inline", non-inline findings with full Why/Suggestion/How to Validate
8. Fetch posted comments, update local report with PR Comment URLs

### Update a review (review-update)
1. Preflight: check staleness — if stale, stop and tell user to validate
2. For each `**PR Comment**` URL in the local report: reply + resolve inline threads, minimize review bodies
3. Run `review-post` to publish the updated verdict
4. Re-link URLs in the local report

### Refresh all reviews (review-refresh)
1. Fetch ALL active reviews from remote + read local report
2. Consolidate: deduplicate, validate, merge findings
3. Close all old comments (resolve inline, minimize review bodies)
4. Overwrite local review file with consolidated report
5. Run `review-post` to publish

## Event mapping
| Assessment | Emote | Event |
|-----------|-------|-------|
| Approved / Approved With Recommendation | ✅ | APPROVE |
| Addressed With Potential Follow-up | ✅ | APPROVE |
| Change Requested / Blocked | ⚠️ / ❌ | REQUEST_CHANGES |

## Common Pitfalls
- Always verify line numbers against current PR diff before posting
- Always update local report with PR URLs after posting
- Use `gh.py interact` for reply/resolve/minimize — it accepts full URLs
- Use `.agents/templates/` for consistent formatting across all review commands
- **Use markdown hyperlinks** when referencing previous reviews or comments — `[text](url)`, never raw IDs like `PRR_abc123`
