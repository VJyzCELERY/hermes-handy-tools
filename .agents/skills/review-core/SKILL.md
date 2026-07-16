---
name: review-core
description: Local review schema, validation, and lifecycle mechanics
license: MIT
compatibility: opencode
metadata:
  type: workflow
---

# Review Core

- Use `.agents/templates/REVIEW-template.md` and rule `004-review-standards.md`.
- Default to `./reviews/REVIEW_{normalized_branch}.md`.
- Run the read-only preflight form in `_common-review-context.md`.
- Form findings without review-log context, then cross-reference exact prior findings.
- Clarify before verify; verify owns status and commit-range updates.
- Keep local review validation separate from GitHub replies and resolutions.
- Use the lifecycle in `.agents/commands/review.md`; do not duplicate it.
- Stop on behind/diverged state. Never pull, stash, reset, commit, or push as review recovery.
