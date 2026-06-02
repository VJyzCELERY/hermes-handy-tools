---
description: Commit conventions, PR guidelines, versioning, deployment
globs: "*.md, *.py"
alwaysApply: false
---

# Commits and PRs

## Commit Messages
Format: `type(scope): description`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `style`
Scope: subproject or module name (e.g., `sdk`, `backend`, `cli`, `preflight`)
Description: imperative, present tense, no period at end

Examples:
- `feat(sdk): add SSE streaming with 4 modes`
- `fix(backend): resolve crash in session creation`
- `docs(readme): update installation guide`

## PR Guidelines
- Title follows conventional commit format
- **PR body MUST use `.agents/templates/PR-body.md` as the template** — populate all sections (Summary, How to Test, Related Issues)
- Body must reference the spec if applicable (link to spec.md / design.md)
- PR targets the appropriate base branch (usually `main`)

## PR Creation Workflow
1. **Always use `uv run python .agents/scripts/gh.py` for ALL PR operations** — create, update, fetch, post, resolve. Raw `gh` CLI is fallback only.
2. **Build the PR body first**: Read the template at `.agents/templates/PR-body.md`, fill in sections based on the spec/design/changes, write to a temp file in `./tmp/pr-body.md`.
3. **Create via gh.py**: `uv run python .agents/scripts/gh.py create "title" ./tmp/pr-body.md [--head <branch>] [--base <branch>]`
4. **On failure**: If gh.py fails with a syntax/transient error, retry once after a 2-second pause. If it still fails, inspect the error output before falling back to raw `gh`.
5. **Verify**: `uv run python .agents/scripts/gh.py fetch pr <pr-number>` to confirm body was set correctly.

## Versioning
- Follow semantic versioning: MAJOR.MINOR.PATCH
- Document breaking changes in CHANGELOG or release notes

## Complexity Limits
- Max function complexity: 10 (radon CC)
- Flag cognitive complexity during review — split complex functions

## Deployment
- Backend: Docker Compose (see `docker-compose.yml`)
- SDK: Published as PyPI package
- CLI: Installed via pip or built as executable
