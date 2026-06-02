---
name: review-archive
description: Logs completed review cycle then archives the review report
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: review-archive — Log and Archive Reviews

## Purpose

Archive a completed review cycle: create a permanent log entry, then move the report to archives for traceability.

## Prerequisites

- A completed review at `./reviews/REVIEW_{branch}.md`
- All findings must be ADDRESSED, INVALID, or DEFERRED (no OPEN)
- Zero-finding (approved) reviews also qualify — no findings to resolve

## Execution

1. Read the review report, extract findings with non-OPEN statuses
2. Create log entry: `uv run python .agents/scripts/review-log.py --log-create "$REVIEW_FILE"`
3. Get entry ID from script output
4. Archive: move report to `./reviews/archives/REVIEW_{branch}_{ID}.md`
5. Validate log: `uv run python .agents/scripts/review-log.py --validate ./reviews/log/REVIEW_{branch}.md`

## Common Pitfalls
- Do NOT archive reviews with OPEN findings
- The log is append-only — never modify existing entries
- Archive filename includes log ID for traceability
- Zero-findings (approved) reviews ARE archived — they get a clean-review approval log entry so no cycle is lost
