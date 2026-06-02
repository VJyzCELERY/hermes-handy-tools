---
description: Closes old review links in the local report, then runs review-post to publish the updated verdict
subtask: true
---

Updates the PR review by first resolving/minimizing all previously linked comments in the local report, then running `review-post` to publish the updated verdict. This is a preprocessing step — the actual posting is handled by `review-post`.

> Load skill: review-pr (for updating PR reviews after fixes)

**Query**: $1 (natural language query or review file path, e.g., "update the PR review from reviews/REVIEW_foo.md" or simply "reviews/REVIEW_foo.md")
**PR Number (Optional)**: $2 (if not provided, detect from current branch or parse from query)


## Overview

> Load _common-preflight.md
> Load skill: gh (for gh.py — all interact operations)

After fixes have been validated (via `review-validate`), this command:
1. Checks that the local report is up to date with the remote PR head (via preflight)
2. Fetches all active review URLs from the local report (both `**PR Comment**` and `**PR Review URL**`)
3. For inline comments: replies documenting the current status, then resolves the thread
4. For non-inline review bodies: minimizes as outdated or resolved
5. Runs `review-post` to publish the updated verdict
6. Re-links the local report with the new URLs

---

## Instructions

### Pre-flight: Check staleness

Run the standard preflight:

> Load _common-preflight.md
> Run `uv run python .agents/scripts/preflight-review.py --scope pr --review-file "$REVIEW_FILE"`
> If it exits non-zero (stale HEAD or unstaged changes), the local report is stale. Print a warning and stop. Tell the user to run `review-validate` first.

### Instructions

1. **Read the updated review report**: Load the REVIEW_{name}.md file — note all `**PR Comment**` URLs and the `**PR Review URL**` in the header.

2. **Detect PR**:
   ```bash
   PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
   ```

3. **Resolve ALL old inline comment threads**: For each finding with a `#discussion_r` URL, these are comments from the PREVIOUS review that is being replaced. Reply with a status update, then resolve the thread so they don't appear in future fetches:
    ```bash
    # Reply documenting that the review has been updated
    uv run python .agents/scripts/gh.py interact reply "$URL" ./tmp/reply.md
    # Always resolve old threads — the new review supersedes them
    uv run python .agents/scripts/gh.py interact resolve "$URL"
    ```
    Do NOT leave old threads unresolved. The new review will contain the updated findings.

4. **Minimize the previous review body**: For the `**PR Review URL**` in the report header, and any non-inline `**PR Comment**` URLs (those with `#pullrequestreview`), minimize as outdated:
    ```bash
    uv run python .agents/scripts/gh.py interact minimize "$URL" --classifier OUTDATED
    ```

5. **Run review-post**: Now that old comments are closed, post the updated verdict:
   ```bash
   # Run /review-post with the same REVIEW file
   ```
   `review-post` will build and post the fresh review with the proper format.

6. **Re-link the local report**: `review-post` now outputs the review URL and inline comment URLs directly in its output. Capture them and update every `**PR Comment**` field in the local report to the new URLs.

---

## Required Context

- Preflight: preflight-review.py
- Skills: review-pr, gh
- Rules: none
- Templates: review-body-snippet.md, inline-comment-format.json
- Mutates files: yes
- Mutates git history: no
- Mutates remote: yes (replies, resolves, posts new review)
- Requires user confirmation: no (but stops if stale)

## Important

- This command ONLY closes old comments and re-links. The actual posting is done by `review-post`.
- Always run the preflight first. If stale, stop and tell user to run `review-validate`.
- Always use `gh.py interact` for all reply/resolve/minimize operations.
- After running, the local report should have updated `**PR Comment**` URLs pointing to the fresh review.
