---
description: Consolidates all existing PR reviews into one fresh review, then runs review-post
subtask: true
---

Consolidate all existing reviews on a PR into a single fresh review. Closes all existing comments (resolves inline, minimizes review bodies), builds a consolidated report, then runs `review-post` to publish.

> Load skill: review-pr (for PR review operations)
> Load skill: review-core (for review report generation)

**Query**: $1 (natural language query or PR number, e.g., "refresh PR #42" or simply "42")
**PR Number (Optional)**: $2 (if not provided, detect from current branch or parse from query)

---

## Overview

After multiple rounds of changes, old review comments may be stale, duplicated, or no longer apply to the current diff. This command:
1. Fetches ALL active (non-minimized) reviews from the remote
2. Fetches the current local review report (if one exists)
3. Consolidates: deduplicates findings from remote + local, drops stale/inapplicable ones
4. Closes all existing active comments (reviews inline, minimizes review bodies)
5. Replaces the local review file with the consolidated report
6. Runs `review-post` to publish the fresh review

---

## Instructions

> Load _common-preflight.md
> Load skill: gh (for gh.py — all fetch/interact/post operations)

1. **Detect PR**: If `$2` is not provided, detect the PR number:
   ```bash
   PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py "$1")
   ```

2. **Get current PR head** (for the commit range):
   ```bash
    HEAD_SHA=$(uv run python .agents/scripts/gh.py cmd pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
    BASE_SHA=$(uv run python .agents/scripts/gh.py cmd pr view "$PR_NUMBER" --json baseRefOid --jq .baseRefOid)
   echo "Refreshing review at commit range: $BASE_SHA...$HEAD_SHA"
   ```

3. **Fetch active reviews from remote** (only non-minimized, non-resolved):
   ```bash
   uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --output ./tmp/remote-reviews.md
   ```
   Read `./tmp/remote-reviews.md` — it contains every non-minimized review with inline comments, each with URLs.
   **IMPORTANT**: Do NOT use `--all` flag. `--all` includes minimized/resolved comments which we don't need for consolidation.

4. **Read the local review report** (if it exists under `./reviews/`):
   ```bash
   ls ./reviews/REVIEW_*.md 2>/dev/null
   ```
   If one exists, read it and note its existing findings.

5. **Consolidate findings**: Merge remote review findings with local report findings:
   - Deduplicate by issue code — if the same code appears in multiple places, keep the most detailed version
   - Drop findings that are clearly addressed or no longer apply
   - Add any new findings from the remote that aren't in the local report
   - The result is a single set of findings

6. **Close all existing active comments**: Use `gh.py interact` on every URL from the remote fetch:
    - Inline comments (`#discussion_r`) → reply documenting the consolidation, then resolve the thread
    - Review bodies (`#pullrequestreview`) → minimize as OUTDATED
    - Skip any thread that has replies from humans (active discussion)
    ```bash
    # Reply first, then resolve (same pattern as review-update)
    uv run python .agents/scripts/gh.py interact reply "$URL" ./tmp/reply.md
    uv run python .agents/scripts/gh.py interact resolve "$URL"
    ```

7. **Write the consolidated local report**: Save the deduplicated findings as `./reviews/REVIEW_{branch}_refreshed.md` using the REVIEW-template.md structure. Do NOT create a new file if one already exists — overwrite the existing one.

8. **Run review-post**: Now that old comments are closed and the local report is ready, delegate to `review-post` to build and post the fresh review:
   ```bash
   # Run /review-post with the consolidated report
   # review-post will handle the posting and URL fetching
   ```

9. **Capture URLs from review-post output**: `review-post` now outputs the review URL and inline comment URLs directly. Capture them from its output and update the consolidated report:
   - Add the new `**PR Review URL**` to the report header
   - For each finding, add or update `**PR Comment**: <url>` with the new inline comment URL

---

## Required Context

- Preflight: preflight-review.py
- Skills: review-pr, review-core, gh
- Rules: none
- Templates: REVIEW-template.md
- Mutates files: yes
- Mutates git history: no
- Mutates remote: yes
- Requires user confirmation: no

## Important

- The goal is **consolidation**. Merge findings from remote + local, deduplicate, then post as one.
- Skip active human discussions — don't close threads that have human replies.
- Overwrite the existing local report — do NOT create a new file.
- Running `review-post` at the end ensures consistent formatting.
