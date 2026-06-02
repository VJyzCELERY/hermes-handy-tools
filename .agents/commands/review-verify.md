---
description: Verifies each finding against latest HEAD and unstaged changes — addressed, invalid, or still OPEN
subtask: true
---

Verify each finding against the current state: run the **How to Validate** command against the latest HEAD. This command does NOT reply to PR comments or update the remote — it only updates the local report. Use `review-update` to push changes to the PR.

> Load skill: review-core (for checking finding statuses)

**Query**: $1 (natural language query or review file path, e.g., "verify the findings in reviews/REVIEW_foo.md" or simply "reviews/REVIEW_foo.md")
**Focus Area (Optional)**: $2 (verify only specific finding codes or severity, e.g., "CRITICAL" or "ISSUE-001,ISSUE-002")

If no focus area is provided, verify ALL OPEN findings.

---

## Cross-Reference Review Log

Before verifying, check if a review log exists for this branch:

```bash
LOG_PATH="./reviews/log/REVIEW_$(git branch --show-current | tr '/' '-').md"
if [ -f "$LOG_PATH" ]; then
    echo "Review log exists: $LOG_PATH"
fi
```

If the log exists, read it and note:
- **Previously deferred items**: If they reappear as OPEN in this review, flag them in the verification — they should be re-checked
- **Previously addressed items**: If they reappear, they may have regressed — flag for attention

## Pre-Flight: Capture current state

> Load _common-preflight.md
> Load skill: gh (for gh.py — used for PR context metadata)

Run the preflight to get scope info (PR number, files changed, commit range). Staleness warnings can be ignored — this command always verifies against whatever HEAD currently is:

```bash
uv run python .agents/scripts/preflight-review.py --scope pr --review-file "$REVIEW_FILE"
```

This captures:
- **Scope info**: PR number, files changed, commit range
- **Unstaged changes**: If present, also run validation commands against unstaged content to check if local edits have resolved the finding

Then proceed with verification — do NOT stop for staleness warnings.

---

## Instructions

1. **Read the Review**: Load the review report from `$REVIEW_FILE` (set by the preflight above). If no file is found, check `./reviews/REVIEW_*.md` for the latest or run the preflight with `--review-file ""` to see the default path.
2. **Run pre-flight checks**: Run the review preflight — if warnings appear, handle staleness or unstaged changes before proceeding
3. **Capture current commit range**: Record the PR head at verification time:
   ```bash
   PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
   echo "Verifying PR #${PR_NUMBER}"
   ```
   Do NOT fetch PR info with `| head -N` or other truncation — you need the full output.

4. **Align Scope**: Check current branch and diff to identify stale findings (files outside current diff → INVALID)
5. **Filter Findings**: If `$2` is provided, only verify those findings
6. **Verify Each Finding**: For each OPEN finding:
   - Execute the "How to Test/Validate" command (use `uv run` for Python)
   - Determine status:
     - Command succeeds → **ADDRESSED**
     - Stale/no longer relevant → **INVALID**
     - Still fails → **OPEN**
   - Document evidence
7. **MANDATORY — Update the Commit Range**: After verification, update the review report's Commit Range to the current HEAD so future staleness detection works correctly:
   ```bash
   uv run python .agents/scripts/update-commit-range.py "$REVIEW_FILE"
   ```
   This is REQUIRED. Without this, staleness detection will always report stale on subsequent runs because the old commit range is never refreshed.

## Status Definitions

- **ADDRESSED**: Issue fixed (validation passes)
- **INVALID**: No longer relevant — including stale findings outside current diff
- **OPEN**: Issue still exists

## Required Context

- Preflight: preflight-review.py
- Skills: review-core
- Rules: 004-review-standards.md
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no (local-only)
- Requires user confirmation: no

## Important

- Run actual validation commands — don't just assume
- Document evidence from command output
- Do NOT rewrite finding content — only update statuses and validation log
- This command is **local-only** — it does NOT reply to PR comments or resolve threads on GitHub. Use `review-update` to push status changes to the remote PR.
- **MUST update Commit Range** after verifying (step 7) — future staleness detection depends on it
- **Do NOT truncate `gh.py` output** when gathering PR info — never pipe through `head`, `tail`, or similar. You need the full output to get all metadata including commit range and body.
