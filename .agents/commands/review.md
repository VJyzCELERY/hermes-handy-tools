---
description: Runs the baseline review lifecycle with optional guarded remote cleanup
---

# Review

**Query**: `$1` optional scope/focus. **Remote cleanup**: explicit `--sync-remote` only.

Read root `AGENTS.md`, rule `004-review-standards.md`, skill `review-core`, `_common-review-context.md`, and the review template. Resolve the report, current HEAD, repository, and PR through shared preflights and `gh.py`.

1. Classify the existing report with `review_workflow.py status`. Stop on MALFORMED or STALE.
2. For ACTIVE_OPEN, delegate `/review-validate` and stop with status counts.
3. For COMPLETE or CLEAN linked to remote feedback, run the always-dry-run `remote-plan` without a sync flag and stop unless `--sync-remote` was passed. With the flag, run `remote-apply --sync-remote` and stop nonzero on partial cleanup.
4. Finalize COMPLETE or CLEAN reports through `review_workflow.py finalize`, which verifies the report against current HEAD, logs by the report's `Branch`, then archives under `reviews/archives/` before creating a fresh report.
5. For ABSENT, perform a fresh independent review and write the canonical report. Auto-finalize a new CLEAN report; otherwise stop with findings.

Remote apply rechecks repository, PR, head, current actor, item authorship, and active human state through `gh.py fetch review-state`; report authorization hints are ignored. It blocks active human discussion, uses marked idempotent replies before resolving inline threads, and minimizes only reviews currently owned by the authenticated actor.

## Mutations

- Local report/log/archive files and, only with `--sync-remote`, linked safe remote feedback. No Git-history, commit, or push mutation.

## Failure

- Stop on malformed/stale reports, ambiguity, failed validation, unsafe or partial remote cleanup, logging, archival, or fresh-review failure.
