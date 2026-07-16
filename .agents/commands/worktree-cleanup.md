---
description: Removes selected ignored artifacts from the current worktree
subtask: true
---

# Worktree Cleanup

**Query**: `$1` one or more of `reviews`, `archives`, `tmp`, `dev`, `agent-local`, `caches`, `logs`; default all.

Read root `AGENTS.md` and load `worktree`. Resolve the current worktree root and inventory only selected ignored artifacts. Never include `.env`, `.env.example`, source, specs, documentation, shared `.agents/`, or files outside this worktree. Show exact paths and size, then remove only that confirmed list. Recreate `./tmp/` when selected.

## Required Context

- Root `AGENTS.md`; skill `worktree`; current worktree root; ignored-artifact inventory.

## Mutations

- Deletes confirmed local ignored artifacts only; no Git-history or remote mutation.

## Confirmation

- Fresh confirmation of the exact path list immediately before deletion.

## Failure

- Stop on unresolved root, path escape, tracked file, unsupported area, or deletion failure; report leftovers.
