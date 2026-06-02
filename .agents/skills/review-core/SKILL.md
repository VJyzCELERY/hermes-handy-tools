---
name: review-core
description: Scoped review, validation pipeline, and loop orchestration
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: review-core — Review, Validate, Verify, Clarify, Loop

## Purpose

Covers the full review lifecycle: scoped code review → clarify vague findings → verify each finding's status → implement fixes → orchestrate review-until-clean cycles.

## Prerequisites

- Load skill: preflight (for preflight-review.py)
- Load skill: gh (for gh.py — PR context, replies, resolution)

## Execution

### Review report
1. Run preflight: `uv run python .agents/scripts/preflight-review.py --scope pr --init-review`
2. Read PR body/title via `gh.py fetch pr`, adjust scope, check compliance
3. Determine scope: PR mode, Branch mode, or Unscoped
4. Analyze in-scope files (Phase 1: unbiased — no log context)
5. Cross-reference findings against review log (Phase 2)
6. Write findings to `./reviews/REVIEW_{name}.md` using `.agents/templates/REVIEW-template.md`

### Clarify
For each OPEN finding: improve location precision, replace vague language, add impact analysis, sharpen validation commands. Do NOT change status.

### Verify
1. Check commit range staleness against current HEAD
2. For each OPEN finding: run validation command (use `uv run` for Python)
3. Determine: passes → ADDRESSED, stale → INVALID, fails → OPEN
4. **MUST update Commit Range** after verification: `uv run python .agents/scripts/update-commit-range.py "$REVIEW_FILE"`
5. This is **local-only** — no PR replies or resolution. Use `review-update` to push status changes to the remote PR.

### Validate (full pipeline)
Run clarify → verify in sequence. Always clarify before verify.

### Loop (orchestration)
1. Report → Validate → If OPEN: Implement → Validate again
2. If CLEAN: Fresh report (new subagent, zero context)
3. If fresh report has issues → back to Validate
4. If fresh report CLEAN → exit → run `/review-archive`

## Common Pitfalls
- Each loop step gets a fresh subagent with zero prior context
- Do NOT fix code yourself — delegate to `/review-implement`
- Documentation is equal priority to code
- Use `uv run` prefix on all Python validation commands
- After validation returns clean, ALWAYS run one more fresh review
- **Do NOT truncate `gh.py` output** when gathering PR info — never pipe through `head`, `tail`, or similar. You need the full output for all metadata, body, and commit range.
- **MUST update Commit Range** after verify — run `update-commit-range.py` to update the review file's commit range so staleness detection works correctly
