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
worktree, command reference, expected and observed evidence, lifecycle status,
question status, and checkpoint.

Goals may contain other goals recursively. Dependencies are separate directed
edges: they block readiness but do not imply ownership. Child policy inherits
from its parent and may narrow authority, never broaden it. Review evidence is
bound to head, base, and diff; any drift invalidates it. Questions answered by
approved state or rules resume the same session; scope, credentials, policy,
external approval, and merge questions become `needs_user`.

Completion requires all required children, dependencies, integration gates,
final verification, and discovered-work dispositions to be resolved. Merge is
always a separately authorized external action.

## Bounded operation

Use isolated `HERMES_HOME` when testing or developing a workflow.
Activation creates the goal directory. Provide goal identity, title, released
template binding, profile and matching mode,
model route, permissions, and policy in one request. Treat the resulting
`config.json` as immutable. Do not copy a repository template into the goal
directory.

Every later mutation names the goal and supplies the revision it observed.
Read `status` or `next` again after a revision conflict; never retry a stale
write with the same number. A failed validation or conflict must leave both
`state.json` and `activity.jsonl` unchanged. Use a new revision only after
inspecting the current state and deciding that the requested transition is
still authorized.

## Evidence and completion

Record a phase only when a worker has an owner, attempt, session/process
identity, command reference, worktree, expected evidence, observed evidence,
and exact next action. The ledger records these claims; it does not verify or
execute them. Record a question when approved state or rules answer it. If the
answer needs scope interpretation, credentials, policy, external approval, or
merge authority, record the escalation and wait for Hermes or a human.

Review evidence is a binding, not a general approval flag. Submit the current
head, base, diff identity, and findings. Any changed binding invalidates older
records. Completion accepts only the latest clean binding, terminal contained
goals, resolved dependency blockers, empty integration blockers, successful
final verification, and no open discovered work. This check makes merge
eligibility observable; it does not authorize or perform the merge.

## Audit and recovery

Successful activation and mutations append one JSONL activity record with a
timestamp, actor, operation, resulting revision, and verified outcome.
Treat the activity file as append-only evidence. If state or an activity record
is malformed, stop and escalate rather than repairing it in place. Preserve
the directory for investigation, report the exact next action, and let the
owning Hermes workflow decide whether to discard and recreate the bounded
goal. Never place credentials, tokens, passwords, private keys, or secret-like
values in titles, findings, questions, evidence, commands, or reasons.

## Resume checklist

1. Read the pinned configuration and state from the isolated home.
2. Confirm the current phase, owner, revision, next action, and readiness.
3. Check child dispositions, dependency blockers, review binding, gates, and
   discovered-work policy before scheduling work.
4. Continue the exact recorded action, or record a question/escalation when
   the evidence or authority is insufficient.
5. After each successful mutation, retain the returned revision as the hand-off
   to the next session.
