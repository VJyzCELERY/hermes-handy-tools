# Development Workflow

## Build, Test, and Development Commands

Always run commands from the subproject root so the correct virtualenv is used.

```bash
# From a subproject directory (e.g., src/my-subproject/)
make install       # install dependencies via uv
make lint          # run Ruff checks and auto-fix
make test          # run pytest unit + integration tests
make coverage      # run tests with coverage report
make complexity    # run radon complexity check
make clean         # remove caches (.pyc, .pytest_cache, .coverage, .ruff_cache)
```

## Important: Always Ask When Uncertain

If any instruction is ambiguous, incomplete, or conflicting, use the question/ask tool to clarify with the user. Do NOT guess or assume. Subagents MUST report questions to their parent orchestrator instead of asking the user directly.

---

## Critical: Always Use `uv run` for Python/Pytest (IMPORTANT)

**All Python and pytest invocations MUST use `uv run`.** Never use bare `python` or `pytest`, as they may import from a different worktree or environment.

```bash
# ✅ CORRECT - uses the project's uv-managed venv
cd <subproject-dir> && uv run python script.py
cd <subproject-dir> && uv run pytest tests/

# ❌ WRONG - may import from wrong worktree or system Python
python script.py
pytest tests/
```

From the repo root (runs all subprojects):
```bash
make lint          # lint all subprojects
make test          # test all subprojects
make clean         # clean all subprojects
```

Pre-commit iteration: run `make lint` repeatedly until all checks pass. Ruff may auto-fix files on first run, requiring a second pass.

---

## Commit Guidelines

All commits must follow the `type(scope): message` format defined in `.agents/docs/project_rules/commit_naming.md`.

**Allowed types:** `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `style`

**Examples:**
```
feat(auth): add user authentication endpoint
fix(auth): resolve null pointer in token refresh
docs(readme): update README with installation steps
test(payment): add unit tests for payment processor
refactor(validation): extract validation logic into helpers
chore(deps): update ruff to 0.4.0
```

**Commit hygiene rules:**
- Keep commits scoped to a single concern; SDK/library changes and application wiring should be separate commits
- Write the message in imperative mood ("add", "fix", "update") not past tense ("added", "fixed")
- Reference issue numbers in the footer when applicable: `Closes #123`

---

## Pull Request Guidelines

Each PR should include:
1. **Descriptive summary** — what changed and why
2. **Testing steps** — how to reproduce or verify (`make test`, specific test names)
3. **Linked issues** — `Closes #123` if applicable
4. **Screenshots or log snippets** — if behavior or output changed visually

Keep PRs scoped: one logical change per PR. Large refactors and feature additions should be separate PRs to ease rollbacks.

---

## Code Review

- Use the review standards in `.agents/docs/agents/code_review.md`
- Always compare against the `main` branch
- Review reports should be saved as `reviews/REVIEW_<branch>.md`
- Reviews are read-only: analyze and report, do not modify code files during a review pass

---

## Feature Development Workflow

0. **Worktree first (if on main)**: If the current branch is `main`, create a worktree via `/begin-worktree <branch-name>` before starting work. This keeps main clean and enables parallel feature branches.
1. **Spec first**: Write or update the spec in `specs/` before writing code (use `.agents/templates/spec.md`)
2. **Design review**: For significant changes, create a `design.md` alongside the spec
3. **Test-first**: Write failing tests before implementation
4. **Implement**: Write the minimum code to make tests pass
5. **Lint + Complexity**: Run `make lint` and `make complexity` — fix all findings
6. **Review**: Open a PR and apply `.agents/docs/agents/code_review.md` standards

---

## References

- `.agents/docs/project_rules/commit_naming.md` — full commit naming rules
- `.agents/docs/agents/code_review.md` — review standards
- `.agents/docs/agents/testing.md` — testing guidelines
