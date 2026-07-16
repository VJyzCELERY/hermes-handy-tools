# Project Guidelines

This file is an orientation map. Normative agent policy lives in the root contract and intent-specific rules, not in this document.

## Canonical Sources

| Concern | Canonical source |
|---|---|
| Repository boundary, permissions, delegation, workflow | `AGENTS.md` |
| Agent behavior, security, and documentation | `.agents/rules/001-agent-behavior.md` |
| Python code standards | `.agents/rules/002-code-standards.md` |
| Python testing | `.agents/rules/003-testing.md` |
| Review standards | `.agents/rules/004-review-standards.md` |
| Project and subproject layout | `.agents/rules/005-project-structure.md` |
| Commits and PRs | `.agents/rules/006-commits-and-prs.md` |
| Spec and design authoring | `.agents/rules/007-spec-design-standards.md` |
| Rebases and Git history rewrites | `.agents/rules/008-git-operations.md` |
| Generated document structure | `.agents/templates/` |
| Command contracts | `.agents/commands/` |
| Reusable tool/domain procedures | `.agents/skills/` |
| Public command inventory | `.agents/commands/README.md` |
| Human-readable workflow orientation | `.agents/docs/guides.md` |

## Project Layout

- `src/` contains subprojects; currently it contains only its explanatory `README.md`.
- `.agents/templates/subproject-template/subproject-generic/` is the language-neutral subproject template.
- `.agents/templates/subproject-template/subproject-python/` is the Python subproject template.
- Issue-centered planning defaults to the primary issue's remote Specs issue. This template checkout's ignored local profile retains `.agents/local/state/artifacts/<issue-key>/`; persist documents only when explicitly requested: project-wide documents use `docs/plans/<feature-name>/`, and subproject documents use `src/<subproject>/specs/<feature-name>/`.
- Feature names and subproject directories use `lower-kebab-case`. Python package and module names use `lower_snake_case`.
- Root agent aliases `.opencode`, `.codex`, `.claude`, and `.hermes` point to `.agents/`.

Use `.agents/templates/spec.md` and `.agents/templates/design.md` directly. The former `specs/spec-template.md` and `specs/design-template.md` paths do not exist in this repository.
