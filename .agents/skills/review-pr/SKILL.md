---
name: review-pr
description: Fetch, post, update, and refresh GitHub review feedback safely
license: MIT
compatibility: opencode
metadata:
  type: workflow
---

# PR Review Operations

Use the `gh` skill, `_common-pr-feedback.md`, and review-post templates.

- Request JSON explicitly for metadata and raw output for diffs.
- Preserve active human discussions.
- Reply before resolving inline threads; minimize superseded review bodies as `OUTDATED`.
- `review-post` is the sole owner of writing fresh GitHub URLs into the local report.
- Stop on stale, behind, diverged, authentication, or remote-write failure.
- Never synchronize Git, fall back to raw `gh`, or post partial feedback after a failed prerequisite.
