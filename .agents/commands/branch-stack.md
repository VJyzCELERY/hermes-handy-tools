---
description: Materializes approved cumulative branches in nested lifecycle worktrees
---

# Branch Stack

Read `_common-branch-context.md`, `_common-branch-lifecycle.md`, and `_common-branch-plan.md` before running this command.

Preview first:

```bash
uv run python .agents/scripts/branch.py stack <lifecycle-id> --json
```

After explicit confirmation to create local branches and nested worktrees:

```bash
uv run python .agents/scripts/branch.py stack <lifecycle-id> --apply --json
```

The source remains the final integration item in its current worktree. Only
prior cumulative slices are created. This command never pushes and never
creates or updates PRs.
