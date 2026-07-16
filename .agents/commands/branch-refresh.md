---
description: Classifies lifecycle drift and optionally rebases a safe local suffix
---

# Branch Refresh

Read `.agents/rules/008-git-operations.md`, `_common-branch-context.md`, and `_common-branch-lifecycle.md` before running this command. Use `_common-branch-plan.md` to preserve the approved slice boundaries and validation dispositions.

Inspect local state, optionally fetching first:

```bash
uv run python .agents/scripts/branch.py refresh <lifecycle-id> [--fetch] [--pr-observations <json>] --json
```

Results classify `fresh`, `local-ahead`, `remote-ahead`, `diverged`,
`missing-remote`, `local-drift`, `stale-base`, or `blocked`, and report the
affected suffix. With a remote, refresh queries authoritative PR state through
`gh.py`; `--pr-observations` accepts equivalent branch-keyed JSON.
Inspection never rebases. After explicit confirmation, a safe stale-base suffix
may be rebased locally with `--apply-rebase`; conflicts roll back all affected
tips. Remote-ahead, diverged, missing, dirty, or ambiguous state blocks rebase.
Lifecycle suffixes use explicit `--onto` boundaries in order; they never fall
back to an implicit rebase.

This command never pushes, force-pushes, or creates or updates PRs.
