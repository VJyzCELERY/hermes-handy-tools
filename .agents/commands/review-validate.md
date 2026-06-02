---
description: Full review validation pipeline — clarifies vague findings, then verifies each one
subtask: true
---

Full review validation: first clarify vague findings, then verify each one's status.

> Load skill: review-core (for the full validation pipeline)

**Query**: $1 (natural language query or review file path, e.g., "validate the findings in reviews/REVIEW_foo.md" or simply "reviews/REVIEW_foo.md")
**Focus Area (Optional)**: $2 (validate only specific finding codes or severity, e.g., "CRITICAL" or "ISSUE-001,ISSUE-002")

If no focus area is provided, validate ALL OPEN findings.

## Pre-Flight

Before running, load the relevant skill and run the review pre-flight:

> Load _common-preflight.md

```bash
uv run python .agents/scripts/preflight-review.py --scope pr --review-file "$1"
```

If it exits non-zero, read the script to recover:

```bash
head -20 .agents/scripts/preflight-review.py
```

---

## Cross-Reference Review Log

Before validating, check if a review log exists for this branch:

```bash
LOG_PATH="./reviews/log/REVIEW_$(git branch --show-current | tr '/' '-').md"
if [ -f "$LOG_PATH" ]; then
    echo "Review log exists: $LOG_PATH"
fi
```

If the log exists, read it and cross-reference:
- **Previously deferred items**: If any deferred items reappear in this review, flag them for re-validation
- **Previously addressed items**: If any addressed items reappear, flag them — they may have regressed
- Note prior cycle findings in the clarify output to give context

---

## Role

`review-validate` runs the complete validation pipeline in two phases:

1. **Clarify** (delegates to `/review-clarify`): improve the precision of each finding
2. **Verify** (delegates to `/review-verify`): check if each finding is addressed, invalid, or still OPEN

---

## Instructions

Run both phases inline by default. Only delegate to subagents if the user explicitly says to use subagents.

### Phase 1: Clarify

Run `/review-clarify` directly:

> Run /review-clarify for $1

This improves finding descriptions, adds missing context, sharpens validation commands.

### Phase 2: Verify

Run `/review-verify` directly:

> Run /review-verify for $1

This runs each finding's validation command and determines its status (ADDRESSED, INVALID, or OPEN).

---

## Required Context

- Preflight: preflight-review.py
- Skills: review-core
- Rules: 004-review-standards.md
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: no

## Important

- Always run clarify BEFORE verify — precise findings lead to accurate validation
- Run steps inline unless the user explicitly requests subagent delegation
- After verify returns, review the report to confirm all findings are properly statused
