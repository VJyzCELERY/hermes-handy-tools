# Review Report: __REVIEW_NAME__

**Directory Reviewed**: [absolute/path/to/directory]
**Review Date**: __REVIEW_DATE__
**Review Type**: [docs|code|pr|full|security|performance]
**Reviewer**: [agent-name or human-name]
**Branch**: __BRANCH_NAME__
**Scope**: __SCOPE__
**Commit Range**: __COMMIT_BASE__...__COMMIT_HEAD__

---

## Summary

[Concise assessment of the reviewed scope and its material risks.]

- **Total Findings**: [N]
- **Critical Issues**: [N]
- **High Issues**: [N]
- **Medium Issues**: [N]
- **Low Issues**: [N]
- **Overall Assessment**: [Approved | Approved With Recommendation | Addressed With Potential Follow-up | Change Requested | Blocked]

---

## Findings

### [CORRECTNESS-PARSER-001] - [HIGH] - Reject malformed review findings

**Status**: OPEN

**Severity**: HIGH

**Category**: CORRECTNESS

**Location**: .agents/scripts/review-log.py:60

**Description**:
The parser silently skips finding headings that do not match its permissive pattern.

**Why It Matters**:
Malformed findings can be mistaken for a clean report and archived without review.

**Suggested Fix**:
Reject any findings section that is neither `No findings.` nor a sequence of complete canonical findings.

**How to Validate**:
```bash
uv run pytest .agents/scripts/tests/test_review_schema.py
```

**Expected Addressed Result**:
The command exits 0 and all malformed finding cases are rejected.

## Remote Feedback

UNLINKED
