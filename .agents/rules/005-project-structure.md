---
description: Project structure, subproject layout, worktree management
globs: "*.md, *.py, *.toml"
alwaysApply: false
---

# Project Structure

## Subproject Layout
All subprojects live under `src/`:
```
src/
├── my-app/          # CLI/TUI application
├── my-backend/      # FastAPI backend
├── my-finetune/     # Fine-tuning pipeline
└── my-sdk/          # Developer SDK
```

## Per-Subproject Standards
- Each subproject has its own `pyproject.toml`, `Makefile`, `tests/`, and `docs/`
- Dependencies between subprojects: SDK → everything else (backend, CLI depend on SDK)
- Use `cd src/<subproject> && uv run` for all commands

## Worktree
- Feature development happens in worktrees, never directly on main
- Worktrees live under `.worktrees/<branch>/`
- To create: `git worktree add .worktrees/<branch> <branch>`
- Before main work: ask for branch name → offer to create worktree

## File Naming
- Source: `snake_case.py`
- Tests: `test_<module>.py`
- Docs: `kebab-case.md` or `UPPER_CASE.md` (templates)
- Reviews: `REVIEW_{branch}.md`

## Review Files
- Active review: `./reviews/REVIEW_{branch}.md`
- Review log: `./reviews/log/REVIEW_{branch}.md`
- Archive: `./reviews/archives/REVIEW_{branch}_{ID}.md`
- All `./reviews/` files are gitignored — never commit
