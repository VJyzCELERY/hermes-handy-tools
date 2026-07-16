---
description: Creates or updates issue-linked single or stacked pull requests
subtask: true
---

# Create PR

**Query**: `$1` optional `OWNER/REPO#NUMBER`. **Mode**: `$2` `single` (default) or `full stack`.

Read root `AGENTS.md`, rule `006-commits-and-prs.md`, `_common-github-ownership.md`, the `gh` skill, `.agents/templates/PR-body.md`, and issue state. If `$1` is omitted, resolve it with `uv run python .agents/scripts/workflow_state.py resolve-active --format json`; otherwise run `uv run python .agents/scripts/workflow_state.py show OWNER/REPO#NUMBER --format json`. Re-fetch the open, non-roadmap, non-`spec`-labelled issue and existing PRs before planning. Use the canonical issue URL as `$TARGET`, then acquire it from the primary checkout:

```bash
PRIMARY=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
TARGET_RESULT=$(cd "$PRIMARY" && uv run python .agents/scripts/resolve-target-worktree.py "$TARGET")
```

Require one returned worktree path for the resolved target, then perform every branch, state, temporary-body, push, and PR operation from that returned worktree.

For `single`, create or update the PR for the recorded/current branch against its actual base. For `full stack`, read validated lifecycle/branch state and create or update every cumulative branch PR in order, with each PR based on its immediate predecessor. Refuse an incomplete or ambiguous stack.

Prepare one filled PR body per branch under `./tmp/`. In the remote profile, render `Specs: #<number>` plus **Spec**, **Design**, **Implementation Plan**, and **Tasks** links copied only from the validated `workflow_state.specs.documents` URLs; never use caller-supplied, guessed, or fetched alternate URLs. Stacked PRs reuse the same references. In the explicit local profile, retain the repository-relative local artifact references instead. The final PR alone contains `Closes OWNER/REPO#NUMBER`; every earlier stacked PR contains `Refs OWNER/REPO#NUMBER` and never `Closes`. Include stack order and neighboring PR links where applicable. Titles follow the commit format.

Preview all branch/base pairs, pushes, titles, bodies, authenticated login, ownership claims, and create/update operations before mutation. Ask one fresh permission for the exact push batch and execute only after approval. Then ask separate fresh permission for the exact GitHub remote write batch; create or idempotently update with `uv run python .agents/scripts/gh.py create <title> <body-file> --head <branch> --base <branch> --draft --format json`. Inherited `/goal` authorization covers only this already-previewed in-scope delivery batch; standalone invocations retain both fresh permissions. New PRs always start as drafts; existing updates preserve their current draft or ready state. Claim every returned PR with `uv run python .agents/scripts/gh.py claim <pr-number> --format json`, preserving existing assignees.

For a standalone metadata-only correction, the exact forms remain `uv run python .agents/scripts/gh.py update title <pr> <title>` and `uv run python .agents/scripts/gh.py update body <pr> <body-file>`.

After each successful create or update, fetch the PR and verify head, base, issue linkage, and body. Record every verified PR, in stack order, with `uv run python .agents/scripts/workflow_state.py set-pr OWNER/REPO#NUMBER <number> --url <url> --head <head> --base <base> --format json`; this preserves partial progress for either single or full-stack resume. Only when the requested set is complete, run `uv run python .agents/scripts/workflow_state.py transition OWNER/REPO#NUMBER pr_open --status active --clear-pending-action --format json`.

## Required Context

- Root `AGENTS.md`; commit/PR rule; `gh` skill; PR template; workflow and optional stack state.

## Mutations

- Confirmed pushes, confirmed PR create or update writes, temporary PR bodies, and ignored workflow state. No commits or history rewrites.

## Confirmation

- Preview first. Outside inherited `/goal` authorization, push permission and remote write permission are separate and fresh; partial approval authorizes only the named batch.

## Failure

- Stop on dirty/uncommitted content, missing remote base, stale/diverged state, malformed stack, duplicate PRs, invalid template body, bad issue linkage, denied permission, or partial remote failure. Record only verified PRs and report the safe resume point.
