---
description: Implements fixes according to review findings — DOES NOT update the review report
subtask: true
---

Implement fixes based on review findings. This command ONLY modifies source code — it does NOT update the review report. Status updates are handled by `review-verify` and `review-validate`.

> Load skill: review-implement (for applying fixes from findings)

**Query**: $1 (natural language query or review file path, e.g., "fix the issues in reviews/REVIEW_foo.md" or simply "reviews/REVIEW_foo.md")
**Focus Area (Optional)**: $2 (implement only specific finding codes or severity, e.g., "CRITICAL" or "ISSUE-001,ISSUE-002")

If no focus area is provided, implement fixes for ALL OPEN findings.

---

## Pre-Flight: Implement Preflight

> Load _common-preflight.md

Run the implement preflight to detect available reviews and check staleness:

```bash
# Auto-detect all reviews for this branch:
uv run python .agents/scripts/preflight-review.py --implement

# Or check a specific review file:
uv run python .agents/scripts/preflight-review.py --implement --review-file "$REVIEW_FILE"
```

The preflight will:
- **Auto-detect mode**: Scan `./reviews/` for REVIEW_*.md files, check each for staleness and branch match. If there's an open PR, also list unresolved PR reviews with fetch commands.
- **File mode**: Check if the specified review exists, verify commit range staleness and branch match.

**If the preflight reports stale reviews or branch mismatches, ask the user before proceeding.** The review may not be applicable to the current code state.

---

## Critical Rule

**DO NOT update the review report.** This command is purely for implementation. The review report is read-only input. Status updates (ADDRESSED, INVALID, OPEN) are handled by `review-verify` and `review-validate`.

---

## Instructions

1. **Read the Review**: Load the review report
2. **Filter Findings**: If `$2` is provided, only fix those findings
3. **Identify OPEN Findings**: Find all findings with status "OPEN"
4. **Review the Suggested Fix**: Read the "Suggested Fix" for each finding
5. **Implement Fixes**: For each OPEN finding:
   - Go to the location specified
   - Implement the fix as suggested
   - Run validation commands to confirm (use `uv run` for Python)
6. **Report**: Tell the user which findings were fixed and that `review-validate` should be run next

## Required Context

- Preflight: preflight-review.py (--implement mode)
- Skills: review-implement
- Rules: 002-code-standards.md
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: yes (if review is stale or scope mismatch)

## Important

- ONLY modify source code — do NOT touch the review report
- After fixing, run validation commands to confirm the fix works
- If validation fails, note what's still wrong
