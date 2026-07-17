# Hermes development log replacement

Use `hermes-devlog` as the local ledger for a bounded Hermes goal. It is not a
journal, backlog, scheduler, daemon, dashboard, or `/goal` replacement; it
preserves resumable workflow state.

## Boundary

The package writes versioned JSON config/state and immutable hash-linked audit
events below `$HERMES_HOME/dev-log/<goal-id>/`. Every mutation is locked, atomic, and
revision-checked. Unknown fields, secret-shaped fields, unsafe identifiers,
unsupported versions, invalid graph edges, permission broadening, illegal
transitions, and stale evidence are rejected. A checkpoint always contains an
exact next action.

The ledger records intent and evidence only. Hermes performs repository,
worker, external-service, notification, and merge actions; the ledger invokes none.

## Workflow

Activate a goal with its released template and commit, command
manifest hash, local snapshot, selected profile, matching mode, governing
sources and permissions. Each route pins model, reasoning, and agent; agent
defaults to `opencode`. The normal semantic baseline is
`issue → plan → implement → implementation review/remediation → PR delivery → final verification → merge-ready`.
Record one owned phase run at a time with attempt, session, process identity,
worktree, command reference, expected and observed evidence, lifecycle status,
question status, and checkpoint. A run's model, reasoning level, and agent
must match its role's route.

Schema v2 stores root semantics in `config.goal` and child semantics in
`state.goal_graph`. Fixed permission booleans control execution: PR requires
push, push requires commit, and merge requires a PR. Policy never grants
authority (`policy.merge` is invalid). `config.governance` only preserves rule
provenance or narrows controls; governance and `extra` cannot grant permission.

Goals may contain other goals recursively. Dependencies are separate directed
edges: they block readiness but do not imply ownership. Child policy inherits
from its parent and may narrow authority, never broaden it. Review evidence is
bound to head, base, and diff; any drift invalidates it. Questions answered by
approved state or rules resume the same session; scope, credentials, policy,
external approval, and merge questions become `needs_user`.

Completion requires resolved children, dependencies, gates, verification, and
discovered work. Merge remains a separately authorized external action.

## Bounded operation

Use isolated `HERMES_HOME` when testing. Activation creates the goal directory.
Use reasoned, revision-checked `amend_config` or `amend_state`; `extra` is
secret-free opaque JSON. Route snapshots remain historical after amendments.

Every later mutation names the goal and supplies the revision it observed.
Read `status` or `next` again after a revision conflict; never retry a stale
write with the same number. A failed validation or conflict must leave both
`state.json` and the audit unchanged. Use a new revision only after
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

Successful mutations write a hash-linked event at `audit/events/<revision>.json`
and advance `audit/HEAD.json`. `audit_list` (100) returns summaries only;
`audit_show` returns an event. If materialized config/state is damaged but the
chain validates, use reasoned `audit_repair`, which records a new revision.
Never place credentials, tokens, passwords, private keys, or secret-like values
in titles, findings, questions, evidence, commands, or reasons.

## Resume checklist

1. Read the pinned configuration and state from the isolated home.
2. Confirm the current phase, owner, revision, next action, and readiness.
3. Check child dispositions, dependency blockers, review binding, gates, and
   discovered-work policy before scheduling work.
4. Continue the exact recorded action, or record a question/escalation when
   the evidence or authority is insufficient.
5. After each successful mutation, retain the returned revision as the hand-off
   to the next session.
