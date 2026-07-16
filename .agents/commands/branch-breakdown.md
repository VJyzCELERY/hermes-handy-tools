---
description: Plans and applies an approved cumulative branch breakdown
---

# Branch Breakdown

Read `_common-branch-context.md`, `_common-branch-lifecycle.md`, and `_common-branch-plan.md` before running this command.

Plan:

```bash
uv run python .agents/scripts/branch.py breakdown --base <base> --lifecycle-id <id> --issue-id <issue> --slice <branch=count> [--slice ...] --json
```

The final `--slice` branch must be the checked-out source branch. Review and
edit the JSON according to `_common-branch-plan.md`, then set `approved` to
`true` only after explicit user confirmation. The source range must be linear;
merge commits are rejected.

Apply the exact approved artifact:

```bash
uv run python .agents/scripts/branch.py breakdown --apply <plan.json> --json
```

Planning does not mutate Git. Approval permits the backup and local rewrite;
it does not permit push, force-push, or PR creation/update.
