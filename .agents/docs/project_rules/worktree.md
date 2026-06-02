# Worktree Management

## Purpose

Git worktrees allow multiple branches to be checked out simultaneously in separate directories. This project uses worktrees for parallel feature development without switching branches.

## Worktree Structure

All worktrees live under `.worktrees/<branch-name>/`:

```
.worktrees/
├── refactor-sdk-v2/
├── stage-04-skills/
└── stage-05-streaming/
```

Each worktree is a fully independent checkout of a branch and has its own `.agents/`, `src/`, etc.

## Creating a Worktree

### Via `/begin-worktree <branch-name>` (recommended)

```
/begin-worktree feat/new-feature
```

This creates both the branch and the worktree in one step.

### Manual Creation

```bash
# 1. Create the branch
git branch feat/new-feature

# 2. Create the worktree
git worktree add .worktrees/feat/new-feature feat/new-feature
```

### Naming Convention

- Worktree directory name must match the branch name
- If the branch contains `/`, replace with `-`
  - Branch: `feat/new-feature` → Worktree dir: `.worktrees/feat-new-feature`
- This keeps the mapping between branch and worktree predictable

### When to Create

- Always create a worktree when the **current branch is `main`** and you want to start new work
- If you already have a feature branch checked out, work on it directly
- The agent should prompt: "What branch name would you like to use?" before creating

## Working in a Worktree

```bash
# Navigate to the worktree
cd .worktrees/<branch-name>/

# All normal git commands work here
git status
git add .
git commit -m "message"

# Return to main worktree
cd /path/to/main/worktree
```

All commands (`/plan`, `/implement`, `/review-report`, etc.) work identically in worktrees because each has its own `.agents/` directory.

## Removing a Worktree

### Via `/worktree-prune` (recommended)

Scans all worktrees, checks PR status, and removes stale ones.

### Manual Removal

```bash
# 1. Ensure branch is merged or abandoned
# 2. Remove the worktree
git worktree remove .worktrees/<branch-name>

# 3. Delete the branch (if merged)
git branch -d <branch-name>

# 4. Delete remote branch (if merged)
git push origin --delete <branch-name>
```

## PRs from Worktrees

When the work is complete and ready for review:

1. Push the branch: `git push origin <branch-name>`
2. Create a PR: `uv run python .agents/scripts/gh.py create "type(scope): title" ./tmp/pr-body.md`
3. The PR will track the worktree's branch automatically

## Best Practices

- **One worktree per feature** — don't stack branches in a single worktree
- **Clean up after merge** — run `/worktree-prune` to remove stale worktrees
- **Keep worktrees rebased** — periodically rebase onto the latest `main` to avoid conflicts
- **Worktrees share the same git objects** — they don't duplicate the repo, only the working tree
