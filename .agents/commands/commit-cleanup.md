---
description: Cleans fixup and duplicate commits from the current branch
subtask: true
---

# Commit Cleanup

**Query**: `$1` target branch, default `main`.

Read root `AGENTS.md`, `.agents/rules/008-git-operations.md`, and commit rules; load `git` and `preflight`. Inspect without mutation:

```bash
uv run python .agents/scripts/preflight-rebase.py --target <target> --list-commits
git log --oneline --graph --decorate <target>..HEAD
git log --oneline --left-right --cherry-pick <target>...HEAD
```

Propose the exact commits and operation. Request fresh permission immediately before each history rewrite. Use the skill's non-interactive method; do not combine meaningful commits unless explicitly requested. Verify the resulting range. A push is a separate action requiring new permission immediately before `git push --force-with-lease origin <branch>`.

## Required Context

- Root `AGENTS.md`; skills `git`, `preflight`; rules `006-commits-and-prs.md` and `008-git-operations.md`.

## Mutations

- Optional local history rewrite; optional separately approved remote force-with-lease push.

## Confirmation

- Fresh permission immediately before every squash/rebase and again before every push. Never infer permission from invoking this command.

## Failure

- Stop on dirty/diverged/protected branches, failed preflight, or conflict. Do not auto-resolve, reset, stash, or push.
