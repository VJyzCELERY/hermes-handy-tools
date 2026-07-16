---
description: Executes an implementation plan using test-first development
subtask: true
---

# Implement

**Query**: `$1` optional issue/PR number or URL. **Focus**: `$2` optional priority.

Read root `AGENTS.md`, rule `006-commits-and-prs.md`, `_common-github-ownership.md`, and coding/testing rules for the affected language. If `$1` is omitted, resolve the active target with `uv run python .agents/scripts/workflow_state.py resolve-active --format json`; otherwise use `$1` as `$TARGET`. Acquire `$TARGET` from the primary checkout before reading or initializing its state:

```bash
PRIMARY=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
TARGET_RESULT=$(cd "$PRIMARY" && uv run python .agents/scripts/resolve-target-worktree.py "$TARGET")
```

Require one returned worktree path for the resolved target, then perform every state, source, test, commit, and push operation from that returned worktree. Re-fetch the open non-roadmap, non-`spec`-labelled issue body and every recorded or branch-matching PR body, head, base, state, and assignees. In the returned worktree, initialize an issue target idempotently from fetched canonical metadata with `uv run python .agents/scripts/workflow_state.py init OWNER/REPO#NUMBER --title <title> --url <url> --objective <objective> --format json` before `uv run python .agents/scripts/workflow_state.py show OWNER/REPO#NUMBER --format json`. For a direct PR target, initialize its PR state with `uv run python .agents/scripts/workflow_state.py init-pr OWNER/REPO!NUMBER --title <title> --url <url> --head <head> --format json`, then validate a reused plan with `uv run python .agents/scripts/workflow_state.py validate-plan-head OWNER/REPO!NUMBER --head <head> --format json`; never use issue-only state lookup for a PR target. Read `spec`, `design`, `plan`, and `task` only from state artifacts in the explicit local profile. In the default remote profile, fetch and validate the complete recorded remote references from the Specs issue before source mutation; remote references are the canonical plan. Refuse caller-supplied alternate artifact paths or remote URLs. Stop if complete plan artifacts are absent in the explicit local profile or complete remote references are absent in the default remote profile; planning is a separate main-agent-dispatched sibling phase.

Before source mutation, preview the authenticated login and selected issue/PR numbers, obtain remote-write confirmation, and claim each with `uv run python .agents/scripts/gh.py claim <issue-or-pr-number> --format json`. Preserve existing assignees and stop if any context or claim fails. Then run `uv run python .agents/scripts/workflow_state.py transition OWNER/REPO#NUMBER implementing --status active --clear-pending-action --format json`. For each task: add the smallest failing test, run it with the project toolchain, implement the minimum fix, rerun focused and relevant suites, and mark the task complete only after evidence passes. When every task and required check passes, run `uv run python .agents/scripts/workflow_state.py transition OWNER/REPO#NUMBER implemented --status active --clear-pending-action --format json`. Preview the verified named paths, commit, and push. After confirmation, commit only those paths and push the returned worktree branch; report implementation evidence to the main agent for separate sibling PR delivery. Do not modify the plan or exceed its scope.

## Required Context

- Root `AGENTS.md`; commit/PR and language-appropriate coding/testing rules; issue/state; complete state artifacts and task file.

## Mutations

- Confirmed issue/PR ownership claims, planned source/tests/docs, state artifact task checkboxes, one commit, and one push.

## Confirmation

- Ask before scope changes. Confirm ownership writes immediately before claiming. Confirm the named commit/push/PR batch immediately before delivery unless `--auto` inherited authorization covers it.

## Failure

- Stop on missing plan/task, unresolved task ambiguity, or failing verification; leave the failed task unchecked and report evidence.
