---
description: Removes confirmed inactive linked worktrees
subtask: true
---

# Worktree Prune

**Query**: `$1` optional linked worktree.

Read root `AGENTS.md`; load `worktree` and `gh`. List worktrees and skip the main worktree. For each candidate, obtain machine-readable PR state:

```bash
git worktree list --porcelain
uv run python .agents/scripts/gh.py cmd --format json pr list --head "$BRANCH" --state all --json number,state,title,baseRefName
```

Keep OPEN PR worktrees. Propose removal for merged, closed, or no-PR branches, including dirty/unpushed status. After per-worktree confirmation, run `git worktree remove <path>` and delete the local branch only when safe. Remote branch deletion is optional and requires separate fresh permission immediately before `git push origin --delete <branch>`.

## Required Context

- Root `AGENTS.md`; skills `worktree`, `gh`; porcelain worktree list; JSON PR state; local branch status.

## Mutations

- Confirmed linked worktree/local branch removal; optional separately approved remote branch deletion.

## Confirmation

- Fresh confirmation per worktree immediately before removal; separate fresh permission before each remote delete push.

## Failure

- Stop for dirty/unpushed work, ambiguous PR state, main worktree, failed removal, or failed branch deletion. Never force removal or hide errors.
