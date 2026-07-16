---
description: Creates a feature worktree and branch
subtask: true
---

# Begin Worktree

**Query**: `$1` issue/PR number or URL.

Read root `AGENTS.md` and load `worktree`. Resolve the explicit target from the primary checkout; the resolver owns safe reuse or creation:

```bash
PRIMARY=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
TARGET_RESULT=$(cd "$PRIMARY" && uv run python .agents/scripts/resolve-target-worktree.py "$1")
```

Require a single returned worktree path and matching target before continuing. Perform all source-aware work from that returned worktree. Report its `action`, `branch`, and `path` from the resolver JSON.

## External Worktrees

To reuse a linked worktree outside the primary checkout, add one `--bypass-guard <absolute-root>` per required external root to `resolve-target-worktree.py`. The option allows only resolved paths beneath those roots for that invocation. To create an external worktree directly, pass the same option and an explicit `--path` to `create-worktree.py`; normal branch validation and rollback remain active.

## Required Context

- Root `AGENTS.md`; skill `worktree`; `resolve-target-worktree.py --help`.

## Mutations

- Reuses or creates one target branch/worktree and local worktree base configuration; no remote mutation.

## Confirmation

- Confirm the explicit target immediately before a resolver call that creates a worktree.

## Failure

- Stop on `[FAIL]`, an ambiguous target, or an invalid returned worktree; follow the resolver diagnostic without pre-creating or repairing branches manually.
