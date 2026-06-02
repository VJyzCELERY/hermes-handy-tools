---
description: Cleans up commit history — squashes fixups, removes duplicates, tidies after rebase
subtask: true
---

Clean up commit history after a rebase: squash fixup commits, remove duplicates, and keep history linear and meaningful.

> Load skill: git (for commit history cleanup)

**Query**: $1 (natural language query — optional target branch, defaults to `main`)

---

## Instructions

## Pre-Flight

Before cleaning up commits, load the relevant skill and run the rebase pre-flight:

> Load skill: preflight (for preflight scripts)
> Load skill: git (for rebase operations)

```bash
uv run python .agents/scripts/preflight-rebase.py --target main --list-commits
```

If it exits non-zero, read the script to recover:

```bash
head -20 .agents/scripts/preflight-rebase.py
```

---

Read `.agents/skills/git/SKILL.md` before proceeding for the full rebase workflow reference.

### 1. Check Current State

```bash
git log --oneline --graph --all --decorate -15
```

Understand the current commit topology.

### 2. Check for Fixup / Squash Commits

```bash
FIXUP_COUNT=$(git log --oneline main..HEAD | grep -c 'fixup!\|squash!')
echo "Fixup/squash commits found: $FIXUP_COUNT"
```

If fixup/squash commits exist, squash them:

```bash
GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash main
```

This auto-squashes fixup/squash commits into their target commits without opening an editor.

### 3. Detect Duplicate Commits

Check for commits that appear in both the current branch and the target (already applied):

```bash
DUPLICATE_COUNT=$(git log --oneline --left-right main...HEAD --cherry-pick | grep '^<' | wc -l)
echo "Duplicate commits found: $DUPLICATE_COUNT"
```

If duplicates exist, rebase to drop them:

```bash
git rebase main
```

Git's default rebase behavior skips commits already in the target.

### 4. Verify Clean History

```bash
echo "=== Commits on branch (unique) ==="
git log --oneline main..HEAD

echo ""
echo "=== Total ==="
git log --oneline main..HEAD | wc -l
```

### 5. Report

Summarize what was cleaned:
- Fixup/squash commits squashed: N
- Duplicate commits removed: N
- Remaining commits on branch: N

---

## Required Context

- Preflight: preflight-rebase.py
- Skills: git, preflight
- Rules: 002-code-standards.md
- Templates: none
- Mutates files: yes
- Mutates git history: yes
- Mutates remote: yes (force push if previously pushed)
- Requires user confirmation: yes (force push requires confirmation)

## Important

- Only clean up commits that are on the current branch (not merged to target)
- Do NOT squash meaningful commits into each other — only fixup! and squash! markers
- After cleanup, force push is required if the branch was previously pushed — use `git push --force-with-lease origin <branch>`, never `--force`. Never force-push `main`/`master`.
- If the branch has no unique commits after cleanup, report that it's ready to merge
