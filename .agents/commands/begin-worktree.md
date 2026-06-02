---
description: Creates a new worktree with a matching branch for feature development
subtask: true
---

Create a new worktree and branch for feature development. Use this when you want to start work without creating specs yet.

> Load skill: worktree (for worktree creation)

**Query**: $1 (natural language — specify the branch name or feature description, e.g., "create a worktree for feat/new-ui" or just "new-ui")

---

## Instructions

1. **Determine branch name**: From `$1`, extract or ask for the branch name:
   - If user provided a name (e.g., "feat/new-ui"), use it
   - If user provided a description (e.g., "I want to build a new UI"), ask: "What branch name would you like to use?"
   - Suggest conventional format: `type/description` (e.g., `feat/new-ui`, `fix/login-bug`)

2. **Create the worktree** using the creation script:
   ```bash
   uv run python .agents/scripts/create-worktree.py <branch-name>
   ```
   The script handles everything: main repo root detection, base branch detection, name sanitization, branch-exists check, and worktree creation. No need to check branch existence beforehand — the script warns and exits if the branch already exists.

3. **Read the output** and report to the user:
   - Worktree path: from `PATH=...`
   - Branch name: from `BRANCH=...`
   - Base branch: from `BASE=...`
   - How to navigate: `cd <PATH>`
   - Next steps: Create specs with `/plan`, or run `/begin-workflow` to start

## Error Handling

If the script exits non-zero, it prints a `[FAIL]` message and an `[ACTION]` instruction telling you what to do next. Follow the `[ACTION]` instruction directly:
- **Branch already exists** → ask the user for a different branch name
- **Invalid name** → suggest the correct format
- **Other errors** → follow the `[ACTION]` instruction printed by the script

## Required Context

- Preflight: none
- Skills: worktree
- Rules: none
- Templates: none
- Mutates files: yes
- Mutates git history: yes
- Mutates remote: no
- Requires user confirmation: no

## Important

- The worktree path is always relative to the main repo root (`$MAIN_REPO/.worktrees/`), even when invoked from inside another worktree
- The new branch is based on the **current branch**, not `main`. This means:
  - PRs will target the current branch automatically
  - Rebasing is straightforward since the base is always the parent branch
- After creating the worktree, you can run `/plan` or `/begin-workflow` inside it
- Use `/implement` to start implementing after specs are ready
