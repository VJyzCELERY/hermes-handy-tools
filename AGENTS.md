# Agent Contract

This repository uses `.agents/` as the canonical, version-controlled agent workspace. `.opencode`, `.codex`, `.claude`, and `.hermes` are tracked relative symlinks to `.agents`; never maintain separate copies through those aliases.

## Authority

When guidance conflicts, use this order:

1. `AGENTS.md`: repository boundary, permissions, and workflow invariants.
2. `.agents/rules/`: normative policy, loaded by intent.
3. `.agents/commands/`: command interfaces and orchestration; commands cannot override this file or loaded rules.
4. `.agents/skills/`: reusable domain and tool procedures.
5. `.agents/templates/`: output structures, not policy.
6. `.github/ISSUE_TEMPLATE/`: human issue forms.
7. `.agents/docs/guides.md`: non-normative orientation.

## Invariants

- At session start, run `uv run python .agents/scripts/preflight-start.py` from the repository root.
- Use `./tmp/` for temporary project files, clean them up, and never use system `/tmp/`.
- Before delegating, explicitly tell every subagent to read the root `AGENTS.md`. Subagents report questions to the parent agent, not the user.
- If instructions are ambiguous, incomplete, or conflicting, ask one concise question and stop rather than guessing.
- Never commit or push without explicit user permission. `--auto`, `/auto`, and a confirmed `/goal` run authorization are explicit permission for their documented command batch; all other permission applies only to the requested batch.
- Never weaken security controls, input validation at trust boundaries, error handling that prevents data loss, accessibility requirements, or explicit permission gates.
- Human issue forms live in `.github/ISSUE_TEMPLATE/`. Agent-created issues should use the applicable form structure.
- Local-only artifacts without a command-defined location belong in `.agents/local/`. Resumable goal, lifecycle, branch, and planning state lives under the ignored `.agents/local/state/`; it is never committed. Command-defined locations such as `reviews/`, `tmp/`, and `.worktrees/` take precedence and must remain uncommitted.

## Load By Intent

Load rules before acting, not during general exploration:

| Intent | Required rules |
|---|---|
| Plan architecture or implementation | `001-agent-behavior.md`, `005-project-structure.md` |
| Write or revise `spec.md` / `design.md` | `007-spec-design-standards.md`, plus `001-agent-behavior.md` and `005-project-structure.md` when designing architecture |
| Write Python | `002-code-standards.md` |
| Write Python tests | `003-testing.md` |
| Review | `004-review-standards.md` |
| Commit or create a PR | `006-commits-and-prs.md` |
| Rebase or rewrite Git history | `008-git-operations.md`, plus `006-commits-and-prs.md` for commits or remote delivery |

## Feature Workflow

Before implementing a feature:

1. Select or create exactly one open, implementation-ready, non-roadmap GitHub issue with `/issue`; the issue is the durable public source of scope and objective.
2. Resume that issue with `/goal`, or invoke its primitive commands directly. Resolve the issue from an explicit `OWNER/REPO#NUMBER` or one unambiguous active state under `.agents/local/state/goals/`.
3. In the default remote profile, publish paired `spec.md` and `design.md` plus implementation artifacts to the primary issue's Specs issue using the matching templates; the explicit ignored local profile retains local artifacts for template development. Resolve all `[NEEDS CLARIFICATION]` markers before implementation.
4. Write a failing test before source code, then implement the minimum change that passes it.
5. Stop only at a clean, verified, issue-linked PR ready for human review; commit, push, and remote-write permissions remain fresh and separate.

Before generating any document, use the matching `.agents/templates/` file. PR bodies must use `.agents/templates/PR-body.md`.

## Tools

- Run repository-owned Python scripts from the root as `uv run python .agents/scripts/<script>.py`.
- Run Python subproject commands from their subproject root, for example `cd src/<subproject> && uv run pytest`. Never invoke bare `python` or `pytest`.
- Run a command's documented preflight first. If it fails, inspect that script's `<EOF_DESC>` guidance before proceeding.
- Use `.agents/scripts/gh.py` for every GitHub operation; use its `cmd` subcommand for operations without a dedicated wrapper.
- Discover public commands only through `.agents/commands/README.md`; command files own their exact behavior.
- Review files under `./reviews/` are local-only and must never be committed or pushed.

## Automation

- Every public command accepts `--auto`. It authorizes that command's documented mutation batch after its required validation and preview; it does not permit unsafe input, conflict resolution, or bypassing failed checks.
- `/auto` enables `--auto` behavior for all commands in the current session. It ends with the session and must not be persisted in repository files.
- `/goal` without `--auto` gathers one complete run authorization before delegated work. `/goal --auto` uses the invocation as that authorization. `/goal --auto-merge` additionally authorizes merging a verified, clean PR.

Discover skills from `.agents/skills/*/SKILL.md`; each skill's frontmatter owns its name and description. Use native skill loading when available, otherwise read the matching file directly.
