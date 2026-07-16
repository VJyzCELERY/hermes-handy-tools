# Hermes development log replacement

Use `hermes-devlog` as the small local ledger for a bounded Hermes goal. It is
not a general journal, backlog, scheduler, daemon, dashboard, or `/goal`
replacement. Its job is to preserve strict state that makes an interrupted
workflow resumable without relying on private worker context.

## Boundary

The package writes versioned JSON state and append-only JSONL activity below
`$HERMES_HOME/dev-log/<goal-id>/`. Every mutation is locked, atomic, and
revision-checked. Unknown fields, secret-shaped fields, unsafe identifiers,
unsupported versions, invalid graph edges, permission broadening, illegal
transitions, and stale evidence are rejected. A checkpoint always contains an
exact next action.

The ledger records intent and evidence only. Hermes remains responsible for
repository inspection, selecting a worktree, launching OpenCode, handling
GitHub, sending notifications, asking a human, and executing or authorizing a
merge. The ledger must never import or invoke those systems, a network client,
tmux, a subprocess, or a notification sender.

## Workflow

Activate a goal with its immutable released template and commit, command
manifest hash, local snapshot, selected profile, matching mode, governing
sources, model route, and allowed permissions. The normal semantic baseline is
`issue → plan → implement → implementation review/remediation → merge-ready`.
Record one owned phase run at a time with attempt, session, process identity,
worktree, command reference, expected and observed evidence, and checkpoint.

Goals may contain other goals recursively. Dependencies are separate directed
edges: they block readiness but do not imply ownership. Child policy inherits
from its parent and may narrow authority, never broaden it. Review evidence is
bound to head, base, and diff; any drift invalidates it. Questions answered by
approved state or rules resume the same session; scope, credentials, policy,
external approval, and merge questions become `needs_user`.

Completion requires all required children, dependencies, integration gates,
final verification, and discovered-work dispositions to be resolved. Merge is
always a separately authorized external action.
