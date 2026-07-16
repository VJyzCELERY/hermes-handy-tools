---
description: Commit naming, pull request content, and release versioning
globs: "*.md"
alwaysApply: false
---

# Commits And Pull Requests

## Commits

- Use `type(scope): description` with an imperative, present-tense description and no trailing period.
- Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, and `style`.
- Use the affected subproject or module as scope when meaningful.
- Keep each commit to one coherent concern. Record breaking changes in the footer.

## Pull Requests

- The title follows the commit format.
- Fill `.agents/templates/PR-body.md`; include summary, verification steps, related issues, and applicable spec/design references.
- Link the primary issue. A standalone or final stacked PR uses `Closes #N`; every earlier stacked PR uses `Refs #N` and must not close the issue.
- Keep the PR scoped to one coherent change and target its actual base branch, which is not necessarily `main` for stacked work.
- Use the `gh` skill and `.agents/scripts/gh.py` for PR operations.

## Versioning

- Use semantic versioning (`MAJOR.MINOR.PATCH`) for versioned releases.
- Document breaking changes in release notes or the project changelog when one exists.
