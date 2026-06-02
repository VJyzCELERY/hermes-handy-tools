---
name: review-implement
description: Apply code fixes from review findings without updating the review report
license: MIT
compatibility: opencode
metadata:
  type: command-skill
  source: .agents/commands/review-implement.md
---

# Skill: review-implement — Apply Fixes from Review Findings

## Purpose

Implement code fixes based on review findings. ONLY modifies source code — does NOT update the review report.

## Critical Rule

**DO NOT update the review report.** Read-only input. Status updates are handled by review-verify and review-validate.

## Execution

1. Read the review report
2. For each OPEN finding: go to Location, implement Suggested Fix, run validation command
3. Always use `uv run` for Python/pytest validation
4. Report which findings were fixed

## Common Pitfalls

- ONLY modify source code — never touch the review report
- Run validation commands after fixing to confirm
- If validation fails, note what's still wrong
