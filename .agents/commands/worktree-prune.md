---
description: Removes inactive worktrees — checks PR status and asks for confirmation
subtask: true
---

Scan all worktrees, check each for PR status, and remove stale ones.

> Load skill: worktree (for removing stale worktrees)

**Query**: $1 (optional — if provided, only prune that specific worktree)

---

## Instructions

1. **List all worktrees**:
   ```bash
   git worktree list
   ```
   Skip the main worktree (the one not in `.worktrees/`).

2. **For each worktree**, determine its fate:

   a. **Get the branch name**: Extract the branch from the worktree path
   b. **Check PR status (all states)**:
       ```bash
        PR_DATA=$(uv run python .agents/scripts/gh.py cmd pr list --head "$BRANCH" --state all --json number,state,title,baseRefName 2>/dev/null)
       ```
   c. **Decision logic**:

   | Condition | Action |
   |-----------|--------|
   | Has OPEN PR | Leave it — work is active |
   | Has MERGED PR | Remove automatically — work is done |
   | Has CLOSED PR | Ask user: "PR was closed without merging. Remove worktree?" |
   | No PR exists | Ask user: "No PR found for this branch. Is it a WIP (keep) or stale (remove)?" |

3. **Remove worktree** (if confirmed):
   ```bash
   git worktree remove .worktrees/<branch-name>
   git branch -d <branch-name>
   git push origin --delete <branch-name> 2>/dev/null || true
   ```

4. **Report summary**: List which worktrees were kept, removed, or need attention

## Required Context

- Preflight: none
- Skills: worktree
- Rules: none
- Templates: none
- Mutates files: yes
- Mutates git history: yes
- Mutates remote: yes (deletes remote branch)
- Requires user confirmation: yes (per worktree)

## Important

- Always skip the main worktree (the one outside `.worktrees/`)
- Always ask for confirmation before removing — never delete a worktree unilaterally
- If `gh` is not authenticated, skip PR checks and ask user manually
- After pruning, run `/worktree-cleanup` if desired

Begin by listing all worktrees and checking PR statuses.
