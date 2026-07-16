---
description: Project, subproject, feature-document, and local-artifact layout
globs: "*.md, *.py, *.toml"
alwaysApply: false
---

# Project Structure

## Subprojects

- Subprojects live at `src/<subproject>/`; directory names use `lower-kebab-case`.
- Use `.agents/templates/subproject-template/subproject-generic/` for a language-neutral subproject or `.agents/templates/subproject-template/subproject-python/` for Python.
- Every subproject owns its source, tests, specs, documentation, dependency configuration, and standard development commands.
- Python configuration (`pyproject.toml`) lives at the subproject root beside its `lower_snake_case` package, not inside the package.
- Python domain or feature subpackages use short `lower_snake_case` names and contain `__init__.py`.

## Feature Documents

- Issue-centered planning defaults to the primary issue's remote Specs issue. The explicit ignored `.agents/local/planning-profile.json` local profile uses `.agents/local/state/artifacts/<issue-key>/` only while developing this template; goal state uses `.agents/local/state/goals/`, lifecycle manifests use `.agents/local/state/lifecycles/`, and branch-local state uses `.agents/local/state/branch.json`.
- Persist project-wide features in `docs/plans/<feature-name>/` only when explicitly requested. Persist single-subproject features in `src/<subproject>/specs/<feature-name>/` only when explicitly requested.
- Feature directories use `lower-kebab-case` and contain paired `spec.md` and `design.md`; never place those files flat in a `specs/` directory.

## Worktrees And Reviews

- Issue branches use `<type>/<issue-number>-<lower-kebab-slug>`.
- Standalone worktrees live under the primary checkout's `.worktrees/`. Lifecycle stack worktrees may live under the source worktree's `.worktrees/` only when created from validated lifecycle state.
- The source worktree owns lifecycle order; each stack worktree stores only its own `.agents/local/state/branch.json` facts.
- Active reviews use `reviews/REVIEW_{normalized_branch}.md`, with `/` in branch names normalized to `_`.
- Review logs and archives remain under `reviews/log/` and `reviews/archives/`. Everything under `reviews/` is local-only.
- Everything under `.agents/local/`, including `.agents/local/state/`, is ignored local state and must never be committed.
