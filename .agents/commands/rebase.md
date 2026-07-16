---
description: Safely rebases the current branch onto a target
subtask: true
---

# Rebase

**Query**: `$1` target branch, default `main`.

Read root `AGENTS.md` and `.agents/rules/008-git-operations.md`; load `git`, `preflight`, and commit rules. Detect stacked ancestry and inspect the requested operation:

```bash
uv run python .agents/scripts/preflight-rebase.py --detect-base
uv run python .agents/scripts/preflight-rebase.py --target <target> --list-commits
```

Resolve and preview the exact old base, new base, branch, affected refs, and command. Request fresh permission immediately before execution.

- For one branch or a non-linear or partially checked-out stack, use `git rebase --onto <new-base> <old-base> <branch>` in lifecycle order.
- For a verified true linear stack, check out its latest affected branch and use `git rebase <new-base> --update-refs`.

On conflict, report files and both sides, then stop for a user decision; stage only each explicitly resolved file before continuing. After `--update-refs`, verify every affected ref because a branch checked out in another worktree is not moved automatically. Verify branch contents with `git log --oneline <target>..HEAD` and `git diff <target>...HEAD --stat`. Any push is separate and requires new permission immediately before `git push --force-with-lease origin <branch>`.

## Required Context

- Root `AGENTS.md`; skills `git`, `preflight`; rules `006-commits-and-prs.md` and `008-git-operations.md`.

## Mutations

- Optional local history rewrite; optional separately approved remote push.

## Confirmation

- Fresh permission immediately before every rebase, conflict resolution, and push.

## Failure

- Stop on failed preflight, dirty/diverged/protected branch, ambiguous base, or conflict. Never stash, reset, pull, auto-resolve, or push as recovery.
