---
description: Generates, inventories, validates, resolves, and harvests stable debt IDs
subtask: true
---

# Debt

**Query**: `$1` `new`, `list`, `check`, `resolve <DEBT-ID>`, or `harvest <DEBT-ID>`.

Read root `AGENTS.md`, `.agents/rules/001-agent-behavior.md`, `_common-github-ownership.md`, `.github/ISSUE_TEMPLATE/technical_debt.yml`, and the `gh` skill.

1. Run local inventory with `uv run python .agents/scripts/debt.py list --format json` or validation with `uv run python .agents/scripts/debt.py check --format json`.
2. Generate an ID with `uv run python .agents/scripts/debt.py new --format json`. This checks tracked markers and all searchable open and closed GitHub issues; stop if remote uniqueness cannot be verified.
3. Resolve an ID with `uv run python .agents/scripts/debt.py resolve DEBT-XXXXXXXX --format json`. Multiple source markers may intentionally share one ID and therefore one issue.
4. For `harvest`, require exactly one valid selected ID in local inventory and resolve it before any write. If an issue already contains the exact ID, return that issue and do not create a duplicate.
5. If no issue exists, use `technical_debt.yml` to render `./tmp/debt-issue-body.md`. Include the exact ID in the title as `[Debt][DEBT-XXXXXXXX]: <summary>` and in the body. Resolve and preview the authenticated login, title, body, labels, and assignees, then request confirmation immediately before `uv run python .agents/scripts/gh.py create-issue <title> ./tmp/debt-issue-body.md --label <labels> --assignee <confirmed-assignee> --format json`. The helper always assigns the authenticated login.
6. Claim the returned issue with `uv run python .agents/scripts/gh.py claim <issue-number> --format json`, then resolve the ID again and report its issue. Never rewrite the source marker: the stable ID is the link shared by collaborators and branches.

## Required Context

- Root `AGENTS.md`; agent behavior rule; technical-debt issue form; `gh` skill.

## Mutations

- `new`, `list`, `check`, and `resolve` are read-only. `harvest` may create one confirmed GitHub issue and an ignored temporary body; it never edits source or Git history.

## Confirmation

- Confirmation is required immediately before issue creation. Resolution and duplicate checks are read-only.

## Failure

- Stop on malformed or missing IDs, failed local validation, unavailable GitHub search, ambiguous issue matches, incomplete issue fields, or rejected confirmation. Never infer issue absence from a failed search.
