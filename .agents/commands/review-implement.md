---
description: Fixes OPEN findings without editing the review report
subtask: true
---

# Review Implement

Focused entrypoint only; it never validates, archives, or starts a review cycle.

**Query**: `$1` optional review path/focus. **Findings**: `$2` optional IDs/severity.

Read root `AGENTS.md`, skills `review-core` and `gh`, applicable coding/testing/commit rules, and `_common-review-context.md`. Run implement preflight; stale, behind, or diverged state blocks work. Treat `$REVIEW_FILE` as read-only. For selected OPEN findings, apply the smallest verified mechanical in-scope fix and run each validation plus relevant tests with the project toolchain. Under inherited `/goal` authorization, commit and push only those verified mechanical fixes before returning remediation evidence; standalone use still requires fresh commit and push permission. Do not make unrelated changes.

If a finding requires PR metadata, prepare the corrected title or `./tmp/pr-body.md` and report it without writing remotely. A separately requested metadata update requires confirmation immediately before the write.

## Required Context

- Root `AGENTS.md`; `_common-review-context.md`; relevant skills/rules; canonical report; PR template only for body fixes.

## Mutations

- Source/tests/docs/config, optional local PR-body preparation, and only under inherited `/goal` authorization the verified mechanical-fix commit and push. Never edits the report.

## Confirmation

- No confirmation for in-scope local fixes. Inherited `/goal` authorization covers only the confirmed mechanical remediation commit/push batch; standalone commit, squash, push, and any remote metadata write need fresh confirmation.

## Failure

- Stop on stale/missing report, failed validation, or metadata write failure. Report remaining OPEN work without changing statuses.
