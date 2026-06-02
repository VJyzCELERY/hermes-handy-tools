---
description: Conducts a scoped code review of the current branch diff and generates a report
subtask: true
---

Conduct a scoped code review of the current branch's changes and generate a comprehensive report.

> Load skill: review-core (for scoped code reviews)

**Query**: $1 (natural language query — specify what to review and optionally the focus, e.g., "review src/my-sdk for security issues" or simply "src/my-subproject/")
**Review Focus (Optional)**: $2 (e.g. "security", "performance", "docs", "unscoped" — parsed from query if not provided)
**Explicit Files (Optional)**: $3 (comma-separated list of files to review outside the diff scope)

## Pre-Flight

Before running, load the relevant skills and run the review pre-flight:

> Load _common-preflight.md
> Load skill: gh (for gh.py — used in PR context)

```bash
uv run python .agents/scripts/preflight-review.py --scope pr --init-review
```

This detects the PR (or branch), determines the commit range, and pre-generates the review file at `./reviews/REVIEW_{branch}.md` with the header and commit range already filled in.

If the pre-flight exits non-zero, read the script's `<EOF_DESC>` to understand what's wrong:

```bash
head -20 .agents/scripts/preflight-review.py
```

After pre-flight succeeds, the review file is ready at `./reviews/REVIEW_{branch}.md`. Read it, then fill in the findings section.

Note: Do NOT pass `--review-file` here — the review report doesn't exist yet. The pre-flight only checks unstaged changes and prints scope info.

---


## PR Context (IMPORTANT — always read when reviewing against a PR)

If reviewing against a PR (detected in scope check below), always read the PR body and title first:

```bash
PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
uv run python .agents/scripts/gh.py fetch pr "$PR_NUMBER" | python -c "import sys,json; d=json.load(sys.stdin); print(f'TITLE: {d[\"title\"]}\n\nBODY:\n{d[\"body\"]}')"
```

Use the PR title and body to **adjust your review scope** — the PR may be narrower or broader than the branch diff. If the PR body/title do not match the actual changes or do not comply with project standards (missing context, no spec references, etc.), flag this as a **finding** with severity MEDIUM. Include a suggestion for what the PR body/title should say.

---

## Scope Determination (IMPORTANT)

This command **must** determine what files are in scope before reviewing. The review is scoped to the branch diff by default.

### Scope Check Steps

1. **Check current branch**:
   ```bash
   git branch --show-current
   ```
   - If branch is `main`, skip to step 4 — no diff scoping needed, review the entire target
   - If branch is detached HEAD, use the merge-base with `main`

2. **Check for an existing PR**:
   ```bash
    uv run python .agents/scripts/preflight-pr.py
   ```
   - If PR exists, record the base branch and PR number
   - The diff base is the PR's base branch (usually `main`)

3. **Determine the diff base**:
   - If PR exists: diff against the PR target branch
   - If no PR: use `git merge-base main HEAD` as the base
   - Record the base commit SHA and the diff range: `<base>...HEAD`
   - Diff command: `git diff <base>...HEAD --name-only`

4. **Record the commit range**: Capture the exact commits being reviewed:
   ```bash
   BASE_SHA=$(git merge-base <base> HEAD 2>/dev/null || git rev-parse <base>)
   HEAD_SHA=$(git rev-parse HEAD)
   COMMIT_RANGE="$BASE_SHA...$HEAD_SHA"
   COMMITS=$(git log --oneline "$COMMIT_RANGE")
   echo "Review range: $COMMIT_RANGE"
   echo "$COMMITS"
   ```

5. **Build the scope list**:

### Scope Rules

- **PR mode**: Only review files changed in the PR (diff against PR base)
- **Branch mode**: Only review files changed on this branch (diff against merge-base)
- **Unscoped mode**: Only when `$2` is "unscoped" — review the full target directory
- **Explicit override**: If user provides `$3`, those files are added to scope regardless of diff

---

---
## Instructions

### Phase 1: Unbiased Review (No Log Context)

1. **Read PR context** (if reviewing against a PR): Follow the PR Context section above — read PR body/title and adjust scope accordingly
2. **Determine scope**: Follow the Scope Determination section above
3. **Analyze scoped files**: Use Read to examine all in-scope files. Do NOT check the review log yet.
4. **Focus Review**: If `$2` is provided (and not "unscoped"), prioritize reviewing for that aspect:
   - "security" — focus on security vulnerabilities
   - "performance" — focus on performance issues
   - "docs" — focus on documentation quality
   - "code" — focus on code quality
   - "full" — comprehensive review (default if no focus)
5. **Identify Findings**: Document issues with clear Issue Codes (e.g., ISSUE-001). Form your own assessment first — unbiased by prior reviews.

### Phase 2: Cross-Reference Against Review Log

Only after you have your preliminary findings, check the review log:

```bash
LOG_PATH="./reviews/log/REVIEW_$(git branch --show-current | tr '/' '-').md"
if [ -f "$LOG_PATH" ]; then
    echo "Review log exists: $LOG_PATH"
fi
```

If the log exists, read it. For each of your preliminary findings:

- **Check if the same issue was previously addressed**: Look for it in prior entries by matching file, line, and description.
  - If found AND the resolution is **properly documented** (clear what was done and why) → mark your finding as INVALID with note: "Already addressed in cycle N — resolution documented."
  - If found BUT the resolution is **not properly documented** (vague or missing reasoning) → keep your finding OPEN, and add a note: "Previously addressed in cycle N but documentation is insufficient — needs proper resolution documentation."
  
- **Check if the same issue was previously deferred**: If found in a prior entry with status "deferred" → note it in your finding: "Previously deferred in cycle N — re-checking."

- **If not found in log at all**: Keep as a new OPEN finding.

### Phase 3: Write Report
5. **Use the pre-generated review file**: The pre-flight already created `./reviews/REVIEW_{name}.md` with the header and commit range pre-filled. Read it, then use Write to fill in the findings section and remove placeholder markers.

## Report Path Convention

Review reports ALWAYS go to `./reviews/REVIEW_{name}.md` (relative to the repo root / workdir).
Do NOT write reviews inside the target directory. This keeps reviews findable at a consistent location.

The `$1` argument is the target being reviewed, NOT the output location.

## Python Validation Commands

```bash
# Always use uv run for Python commands
cd <subproject-dir> && uv run python -c "..."
cd <subproject-dir> && uv run pytest tests/...

# ❌ Wrong - bare python/pytest may import from wrong worktree
python ...
pytest ...
```

## Report Filename

Use format: `REVIEW_{name}.md`

## Review Report Format

```markdown
# Review Report: [Project Name]

**Directory Reviewed**: [absolute/path]
**Review Date**: [YYYY-MM-DD]
**Scope**: [branch diff | PR #N | unscoped]
**Review Focus**: [focus or "full"]
**Reviewer**: Code Reviewer
**Commit Range**: [base_sha...head_sha]
**Overall Assessment**: [Approved | Approved With Recommendation | Change Requested | Blocked]

---

## Summary

[Brief summary of what was reviewed — mention the scope]

---

## Findings

### [ISSUE-001] - [CRITICAL] - [Issue Name]

**Status**: OPEN

**Severity**: CRITICAL

[Detailed description of the issue]

**Location**: [file:line number]

**How to Test/Validate**:
```bash
[Command to check for this issue — MUST use uv run]
```

**Suggested Fix**:
[Description of how to fix]
```

## Important

- **Check template first**: Read `.agents/templates/REVIEW-template.md` before generating the report — follow its structure
- MUST determine scope before reviewing
- MUST scope the review to the current branch diff unless unscoped
- **Documentation is equal priority to code** — flag missing/stale docs with same severity as code bugs
- **PR body/title compliance** — if reviewing against a PR, always check that the PR body and title accurately reflect the changes and comply with spec references. Flag non-compliance as a finding
- **Record the commit range** in the review header — this lets the user know if the review is stale (new commits since review)
- MUST create the review file at `./reviews/REVIEW_{name}.md` — it is gitignored, do NOT `git add` or commit it
- Each finding MUST include an executable validation command (prefixed with `uv run`)
- Use proper Issue Codes (ISSUE-001, ISSUE-002, etc.)
- Categorize findings by severity
- **Set the Overall Assessment** based on findings:
   - **Approved**: No issues found (approve directly)
   - **Approved With Recommendation**: Minor issues (MEDIUM/LOW) that don't block merge
   - **Addressed With Potential Follow-up**: All issues closed but may warrant a fresh review in the future when the PR changes scope
   - **Change Requested**: Any HIGH or CRITICAL issues that must be fixed
  - **Blocked**: Issues that violate spec, introduce regressions, or break tests
- If scope is empty (no files changed), report that and exit

## Required Context

- Preflight: preflight-review.py (--init-review)
- Skills: review-core, gh
- Rules: 004-review-standards.md
- Templates: REVIEW-template.md
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: no

Begin by checking the current branch and determining review scope, then analyze files and write the report.
