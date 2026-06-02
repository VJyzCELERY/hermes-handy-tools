---
description: Cleans up local artifacts in the current worktree (reviews, dev, tmp, etc.)
subtask: true
---

Clean up local development artifacts in the current worktree: reviews, dev folders, tmp files, and other gitignored caches.

> Load skill: worktree (for cleaning worktree artifacts)

**Query**: $1 (optional — specific area to clean, e.g. "reviews", "tmp", "caches")

If no query is provided, clean ALL artifact areas.

---

## Instructions

1. **Identify the worktree root**: This is the directory containing `.gitignore`
2. **Clean artifact areas** (skip `.env` and `.env.example`):

   | Area | What to remove | Command |
   |------|---------------|---------|
   | Review files | All `./reviews/*.md` except archived | `rm -f ./reviews/REVIEW_*.md` |
    | Archived reviews | `./reviews/archives/*.md` | `rm -rf ./reviews/archives/` |
   | Temp files | `./tmp/` | `rm -rf ./tmp/ && mkdir ./tmp/` |
   | Dev artifacts | `./dev/` | `rm -rf ./dev/` |
   | Cache dirs | `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.coverage`, `htmlcov` | `rm -rf ./**/__pycache__ ./**/.pytest_cache ./**/.ruff_cache ./**/.coverage ./**/htmlcov` 2>/dev/null |
   | Logs | `logs/` | `rm -rf ./logs/` |

3. **Report**: List what was cleaned and how much space was freed

## Required Context

- Preflight: none
- Skills: worktree
- Rules: none
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: yes (destructive — removes artifacts)

## Important

- **NEVER** remove `.env` or `.env.example` files
- **NEVER** remove source code, specs, or documentation
- If `$1` is provided (e.g., "reviews"), only clean that specific area
- Use `rm -f` to avoid errors on non-existent files
- This command only affects the current worktree, not other worktrees or the main repo

Begin by identifying the worktree root and cleaning artifact areas.
