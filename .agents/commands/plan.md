---
description: Creates remote Specs revisions or explicit local planning artifacts
subtask: true
---

# Plan

**Query**: `$1` optional `OWNER/REPO#NUMBER`. **Context**: `$2` optional priorities.

Read root `AGENTS.md`, rules `001`, `005`, and `007`, and all four planning templates. If `$1` is omitted, resolve it with `uv run python .agents/scripts/workflow_state.py resolve-active --format json`; otherwise run `uv run python .agents/scripts/workflow_state.py show OWNER/REPO#NUMBER --format json`. Re-fetch the open non-roadmap issue and use its canonical URL as `$TARGET`. From the primary checkout, acquire the target worktree:

```bash
PRIMARY=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
TARGET_RESULT=$(cd "$PRIMARY" && uv run python .agents/scripts/resolve-target-worktree.py "$TARGET")
```

Require one returned worktree path for the resolved target, then perform every state, artifact, and template operation from that returned worktree. The default profile is remote. Create the four complete documents from the templates under `./tmp/` and resolve every clarification marker. Preview the exact remote Specs mutations: `specs ensure` may create the `spec` label, create or reuse the Specs issue, and link the primary issue; `specs publish` will append up to four document comments and update the Specs revision index. Require fresh remote-write confirmation immediately before that batch, except when inherited `--auto` authorizes the previewed batch. Then use `uv run python .agents/scripts/gh.py specs ensure <primary-issue> <primary-title> --format json`, which links the primary issue to its Specs issue, and `uv run python .agents/scripts/gh.py specs publish <specs-number> --primary <primary-number> --revision <next-revision> --spec <spec> --design <design> --plan <plan> --task <task> --format json`. Record the complete validated issue, index, and document comment references with `workflow_state.py set-specs`; remove temporary documents after state is written. Do not create local canonical planning paths in the remote profile.

An explicit ignored `.agents/local/planning-profile.json` containing `{"profile":"local"}` is reserved for development of this template repository. Only this local profile uses the prior issue-keyed `.agents/local/state/artifacts/` flow and `uv run python .agents/scripts/workflow_state.py set-artifacts OWNER/REPO#NUMBER --directory <directory> --spec <spec> --design <design> --plan <plan> --task <task> --format json`. In either profile, after all records validate, run `uv run python .agents/scripts/workflow_state.py transition OWNER/REPO#NUMBER planned --status active --clear-pending-action --format json`. Do not change source code.

## Required Context

- Root `AGENTS.md`; rules `001-agent-behavior.md`, `005-project-structure.md`, `007-spec-design-standards.md`; issue/state; planning templates.

## Mutations

- Remote profile: may create the `spec` label and Specs issue, link the primary issue, append up to four document comments, update the Specs revision index, and write Specs references and planning phase to ignored local state.
- Local profile: creates or updates only state artifacts `spec.md`, `design.md`, `implementation-plan.md`, and `task.md` in the issue's ignored artifact directory, plus artifact paths and planning phase in state.

## Confirmation

- Preview remote Specs mutations and require fresh remote-write confirmation immediately before them, except for inherited `--auto`. Ask separately when issue, project/subproject, or requirements are ambiguous. No Git action is permitted.

## Failure

- Stop on missing templates, issue/state conflict, closed/roadmap issue, unresolved clarification, or unsafe artifact path; do not invent requirements.
