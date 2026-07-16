---
description: Selects or creates one implementation-ready GitHub issue
subtask: true
---

# Issue

**Query**: `$1` `existing <number-or-url>` or `create <bug|feature>`. **Context**: `$2` issue details.

Read root `AGENTS.md`, `.github/ISSUE_TEMPLATE/`, and the `gh` skill. This command owns issue selection and creation only; roadmap and `spec`-labelled issues are not implementation goals. It never claims work or creates workflow state, a branch, a worktree, a commit, or a PR.

1. For `existing`, fetch JSON with `uv run python .agents/scripts/gh.py fetch issue <issue> --format json`. Require an open, non-roadmap, non-`spec`-labelled issue in the current repository.
2. For `create`, choose `bug_report.yml` or `feature_request.yml`, collect every required form field, render `./tmp/issue-body.md` with the form's headings, and search open and closed issues for duplicate titles, terms, and scope. Present likely duplicates instead of creating another issue.
3. Perform a readiness check: one coherent outcome, identified project/subproject, testable acceptance behavior, constraints, and no unresolved blocking ambiguity. Ask concise questions until ready; do not silently expand scope.
4. Preview the exact title, body, labels, and unclaimed status. Ask for confirmation immediately before the GitHub write, then create the issue with `uv run python .agents/scripts/gh.py create-issue <title> ./tmp/issue-body.md --label <labels> --unclaimed --format json`.
5. Fetch the returned issue and require its canonical URL, repository, open state, non-roadmap status, and no assignees. Return its normalized `OWNER/REPO#NUMBER` identity and URL. `/implement` or `/goal` claims the issue only when work begins.

## Required Context

- Root `AGENTS.md`; `gh` skill; applicable human issue form; `gh.py` issue operations.

## Mutations

- Optional confirmed GitHub issue creation and temporary body. No local workflow state, source, Git-history, branch, worktree, commit, push, or PR mutation.

## Confirmation

- Confirmation is required immediately before `create-issue`. Existing issue reads and duplicate/readiness checks are read-only.

## Failure

- Stop on malformed GitHub JSON, repository mismatch, closed/roadmap issue, duplicate risk, incomplete form, failed readiness, or rejected confirmation. Never treat a failed fetch as issue absence.
