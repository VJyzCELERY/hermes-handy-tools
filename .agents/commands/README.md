# Command Workflows

This table is the canonical inventory of public commands currently available. Files beginning with an underscore are internal shared modules, not commands.

| Command | Workflow | Purpose |
|---|---|---|
| `/auto` | Automation | Enable `--auto` behavior for all commands in the current session |
| `/begin-worktree` | Worktrees | Create a feature branch and linked worktree |
| `/branch-breakdown` | Branch lifecycle | Plan and apply an approved cumulative branch breakdown |
| `/branch-refresh` | Branch lifecycle | Classify stack drift and optionally rebase a safe local suffix |
| `/branch-stack` | Branch lifecycle | Materialize cumulative branches in lifecycle worktrees |
| `/commit-cleanup` | Git history | Clean fixup and duplicate commits |
| `/create-pr` | Feature delivery | Create or update issue-linked single or stacked PRs |
| `/debt` | Code quality | Generate, inventory, validate, resolve, and harvest stable debt IDs |
| `/goal` | Feature delivery | Resume one issue through a merge-ready PR |
| `/implement` | Feature delivery | Execute an implementation plan test-first |
| `/issue` | Feature delivery | Select or create one implementation-ready issue |
| `/plan` | Feature delivery | Create implementation plan and task documents |
| `/rebase` | Git history | Rebase the current branch safely |
| `/review` | Local review | Run baseline review and finalize completed prior cycles |
| `/review-archive` | Local review | Log and archive a completed review |
| `/review-fetch` | PR review | Merge remote feedback into the local report |
| `/review-implement` | Local review | Fix open findings without editing the report |
| `/review-post` | PR review | Post the local report as a PR review |
| `/review-refresh` | PR review | Consolidate and replace active PR feedback |
| `/review-update` | PR review | Replace linked PR feedback with the current verdict |
| `/review-validate` | Local review | Clarify and verify findings |
| `/setup-project` | Infrastructure | Initialize or update repository agent infrastructure |
| `/worktree-cleanup` | Worktrees | Remove selected ignored worktree artifacts |
| `/worktree-prune` | Worktrees | Remove confirmed inactive linked worktrees |

## Automation

Every public command accepts an optional trailing `--auto`. It authorizes the
command's documented mutation batch after validation and preview. `/auto`
applies the same behavior to all commands in the current session. `/goal`
collects one complete run authorization when `--auto` is absent; use
`--auto-merge` only when the final verified PR should also be merged.

## Recommended Flows

### Issue Delivery

`/issue` → `/goal`

`/goal` acquires the issue worktree and directly dispatches sibling planning, implementation, PR delivery, and review phases until the PR is verified merge-ready. Invoke primitive commands directly when only one phase is needed.

### Large Branch Delivery

`/branch-breakdown` → `/branch-stack` → `/create-pr` → `/branch-refresh` as needed

Breakdown requires an approved local plan before rewriting. Stack creates local branches/worktrees only. Push and PR creation remain owned by `/create-pr`.

### Review

`/review` → optional `/review-validate` → optional `/review-implement` → `/review`

Use `/review-post`, `/review-update`, or `/review-refresh` only for explicit GitHub review publication or synchronization. Remote cleanup from baseline review requires `--sync-remote`.

### Technical Debt

Use `/debt new` before recording an intentional compromise, `/debt check` to validate tracked markers and production stubs, and `/debt harvest DEBT-XXXXXXXX` when the debt warrants a GitHub issue. Harvest resolves existing open and closed issues first and never rewrites source markers.
