---
description: Safely rebases current branch onto target — avoids duplicating already-applied commits
subtask: true
---

Safely rebase the current branch onto a target branch (default: `main`) without duplicating commits that are already in the target history.

> Load skill: git (for safe rebasing)

**Query**: $1 (natural language query — specify the target branch, e.g., "rebase onto main" or simply "main")
**Target Branch**: (parsed from query, defaults to `main`)

---

## Instructions

> Load skill: preflight (for preflight-rebase.py)
> Load skill: git (for rebase operations)

### 1. Run Pre-Flight

```bash
uv run python .agents/scripts/preflight-rebase.py --target <target>
```

Review any warnings before proceeding. If critical issues are flagged, address them first.

### 2. Check Current State

```bash
git log --oneline --graph --all --decorate -10
```

Understand where the current branch is relative to the target.

### 2. Check for Already-Applied Commits

Before rebasing, check if any commits on the current branch are already in the target:

```bash
# List commits on current branch NOT in target
UNIQUE_COMMITS=$(git log --oneline <target>..HEAD)

if [ -z "$UNIQUE_COMMITS" ]; then
  echo "No unique commits — branch is already up to date with target."
  exit 0
fi

# Check if any commits are already applied (cherry-picked or merged)
git log --oneline HEAD --not <target> --cherry-pick
```

Use `--cherry-pick` or `--fork-point` to detect commits that have already been applied elsewhere:

```bash
git merge-base --fork-point <target> HEAD
```

### 3. Perform the Rebase

```bash
git rebase <target>
```

- If `git rebase` warns about skipped commits (already applied), use `--reapply-cherry-picks` only if intentionally needed
- Normally, skipped commits should NOT be reapplied — they're already in the target

### 4. Handle Conflicts

If `git rebase <target>` fails with conflicts, do NOT resolve silently. Involve the user:

#### 4a. Notify the User

Use the question/ask tool to tell the user a conflict occurred (priority). Only write inline if your harness has no such tool. Do NOT try to auto-resolve without user input.

#### 4b. Analyze the Conflicts

```bash
git status                         # show which files have conflicts
```

For each conflicted file, examine the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`):

```bash
# Show conflict regions with line numbers
grep -rn '<<<<<<<\|=======\|>>>>>>>' <conflicted-file>
```

#### 4c. Present to the User

For each conflict, tell the user:
- **File**: The file path
- **Lines**: The line range of the conflict
- **What changed on YOUR branch**: The commit message and what it changed
- **What changed on THEIRS (target)**: The commit message and what it changed
- **Suggested resolution**: Recommend which side to keep, or how to merge both
- **Ask for their input**: Use the question/ask tool to ask the user how to proceed

Example:
```
Conflict in src/agent.py:45-52

Your branch (feat/new-feature): "Add timeout handling" — added try/except around API call
Target (main): "Refactor error handling" — moved error handling to middleware

Suggested: Keep both — wrap the try/except with the new middleware pattern.
How would you like to resolve this?
```

#### 4d. Apply the User's Decision

Once the user tells you what to do:
1. Edit the file accordingly
2. Remove conflict markers
3. Stage the resolved file: `git add <resolved-file>`
4. Continue: `git rebase --continue`

#### 4e. Repeat

If there are multiple conflicts, repeat steps 4b-4d for each one. Conflicts are resolved one commit at a time — you may encounter the same file in a later commit with different conflicts.

#### 4f. Abort Option

If the user wants to stop the rebase entirely:

```bash
git rebase --abort
```

Provide this option at any point if the user seems unsure.

### 5. Verify After Rebase

```bash
git log --oneline --graph --all --decorate -10
git diff <target>...HEAD --stat   # what changed vs target
```

### 6. Skip If No Change Needed

If after checking, the branch has no unique, meaningful commits (only merge commits or already-applied commits), exit cleanly:

```bash
if [ "$(git log --oneline <target>..HEAD | wc -l)" -eq 0 ]; then
  echo "Branch is already up to date — nothing to rebase."
  exit 0
fi
```

---

## Required Context

- Preflight: preflight-rebase.py
- Skills: git, preflight
- Rules: none
- Templates: none
- Mutates files: yes
- Mutates git history: yes
- Mutates remote: yes (force push with lease)
- Requires user confirmation: yes (conflict resolution, force push)

## Important

- Read the git-rebase skill before executing
- Always check for already-applied commits before rebasing
- Never use `--reapply-cherry-picks` unless you explicitly want duplicates
- After rebasing, force push is required (`git push --force-with-lease origin <branch>`) — use `--force-with-lease` to avoid overwriting others' changes. Never force-push `main`/`master`.
- **Conflicts must involve the user** — analyze and present each conflict, recommend a resolution, and ask for input using the question/ask tool (priority; inline if tool unavailable). Never resolve conflicts silently.
- Use the question/ask tool at every step that needs user input — don't proceed with assumptions

Begin by reading the git-rebase skill, then check the current branch state and rebase onto the target.
