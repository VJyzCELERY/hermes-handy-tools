---
name: worktree
description: Create, prune, and clean up git worktrees
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: worktree — Worktree Management

## Purpose

Manage git worktrees: create new worktrees for feature development, prune inactive ones, and clean up local artifacts.

## Execution

### Create worktree
1. Ask for branch name (e.g., "feat/new-ui")
2. Run:
   ```bash
   uv run python .agents/scripts/create-worktree.py <branch-name>
   ```
   The script handles everything: branch-exists check, main repo root detection, base branch detection, name sanitization, and creation. No need to pre-verify — the script will warn with `[ACTION]` instructions if something is wrong.
3. Read output: `BRANCH=...`, `PATH=...`, `BASE=...`
4. Report the results to the user — tell them the branch name, absolute path, and base branch

### Prune worktrees
1. List all worktrees: `git worktree list`
2. For each linked worktree: check if branch has an open PR
3. If PR is merged/closed and branch is safe to remove: `git worktree remove <path>`

### Clean up
1. Remove review files: `rm -f ./reviews/REVIEW_*.md`
2. Clean tmp directory: `rm -rf ./tmp/*`
3. Clean unspecified agent-local artifacts: `rm -rf ./.agents/local/`
4. Remove pycache: `find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null`

## Common Pitfalls
- The script handles branch-exists checks, name sanitization, and path resolution — do NOT pre-verify, just run it
- The new branch is based on the **current branch**, not `main`. This ensures PRs target the correct parent
- Ordinary worktree paths are under `<main_repo_root>/.worktrees/`. Only `/branch-stack` lifecycle worktrees may be nested under their source worktree as defined by lifecycle state.
- Only prune worktrees whose PRs are merged or abandoned
- Always verify before destructive operations
- Preserve shared `.agents/` infrastructure; only `.agents/local/` is an agent-local cleanup target
