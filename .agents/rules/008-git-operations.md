---
description: Normative safety rules for rebases and other Git history rewrites
globs: "*.md, *.py"
alwaysApply: false
---

# Git Operations

## Rebase Forms

- Do not rebase unless the active command or user explicitly requests it. Run the documented rebase preflight first and stop on dirty, ambiguous, remote-ahead, diverged, or conflicting state.
- When moving a branch from one known old base to another, use `git rebase --onto <new-base> <old-base> <branch>`.
- For a verified true linear stack, check out the latest affected branch and use `git rebase <new-base> --update-refs` so Git moves eligible intermediate refs together.
- Never start a history-moving rebase without either `--onto` or `--update-refs`. The `git pull --rebase` form is prohibited because it hides the old boundary.
- Rebase control operations using `--abort`, `--continue`, `--skip`, or `--quit` are exempt because they do not start a new history rewrite.

## Stack Safety

- Use `--update-refs` only after verifying true linear ancestry and the complete affected ref set. Git does not update a branch checked out in another worktree; verify every affected ref afterward and handle skipped refs explicitly.
- If topology is not a verified true linear stack, rebase each affected branch in lifecycle order with explicit `--onto` boundaries.
- Stop immediately on ambiguity, a failed earlier rebase, or conflict. Never auto-resolve conflicts.

## Remote Safety

- Rebase permission does not grant push permission. Request fresh confirmation before each remote history rewrite.
- Push rewritten branches only with `--force-with-lease`. Preserve lifecycle order for stack pushes.
