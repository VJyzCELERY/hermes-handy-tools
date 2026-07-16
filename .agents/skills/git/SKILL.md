---
name: git
description: Rebase branches, clean up commit history safely
license: MIT
compatibility: opencode
metadata:
  type: infrastructure
---

# Skill: git — Rebase and Commit Cleanup

## Purpose

Safely rebase branches onto targets without duplicating commits, and clean up commit history by squashing fixups and removing duplicates.

## Prerequisites

- Load skill: preflight (for preflight-rebase.py)
- Read `.agents/rules/008-git-operations.md`; it is the normative rebase policy.

## Execution

### Rebase — Always detect stacked branches first

**Default behavior is stacked rebase.** Before rebasing onto the requested target, detect whether this branch is built on top of another local branch:

1. **Detect the true base**: `uv run python .agents/scripts/preflight-rebase.py --detect-base`
   - First checks if branch has an open PR on GitHub — if so, uses the PR's target base (`source=pr`)
   - If no PR exists, falls back to finding the tightest local ancestor branch (`source=local`)
   - If output says `base=<branch>` where `<branch>` is not `main`/`master`, the branch is **stacked**.
   - If it says `base=main`, the branch is a **single** (standalone) branch.
2. **If stacked** (branch is built on another local branch):
   - Identify the parent branch (e.g., `base/refactor-sdk-v2`)
   - Check parent's own base: if parent is also stacked, resolve recursively until reaching `main`
   - **Always rebase from bottom up**: rebase the parent branch onto `main` first, then rebase this branch onto the rebased parent
   - Follow the "Stacked Rebase" workflow below
3. **If single** (branch builds directly on `main`):
   - Follow the "Single Branch Rebase" workflow below

### Single Branch Rebase
1. Run preflight: `uv run python .agents/scripts/preflight-rebase.py --target <target>`
2. Check for already-applied commits: `git log --oneline <target>..HEAD`
3. If no unique commits, exit early
4. Resolve the old merge base and run `git rebase --onto <target> <old-base> <branch>`
5. If conflicts: analyze, present to user, apply their decision
6. With explicit push permission, force push: `git push --force-with-lease origin <branch>`

### Stacked Rebase
Use when a branch is built on top of another local branch (not `main`).

1. **Identify the stack**: use `--detect-base` to confirm the parent chain
2. **Rebase parent first** (recurse if parent is also stacked):
   - Switch to parent worktree/branch
   - Rebase parent onto `main` (or its own parent)
    - With explicit push permission, force push parent with `--force-with-lease`
3. **Rebase this branch onto rebased parent** with its recorded old parent:
    ```bash
    git rebase --onto <parent-branch> <old-parent> <branch>
    ```
   For a verified true linear stack whose affected intermediate refs are not checked out elsewhere, the latest affected branch may instead use `git rebase <new-base> --update-refs`; verify every affected ref afterward.
4. **Force push**: with explicit push permission, run `git push --force-with-lease origin <branch>`
5. **Verify**: check `git log --oneline <parent-branch>..HEAD` shows only this branch's unique commits

### Commit cleanup
1. List recent commits: `git log --oneline -20`
2. Identify fixup/revert/duplicate commits
3. Interactive rebasing is not supported — use soft reset instead:
   - `git reset --soft <base>` + `git commit -m "message"`
4. Verify the cleaned history

## Common Pitfalls
- Never use `--reapply-cherry-picks` unless intentionally needed
- Always involve the user for conflict resolution — never auto-resolve
- Check commits are not already in target before rebasing
