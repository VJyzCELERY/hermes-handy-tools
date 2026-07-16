# Common Branch Lifecycle

Lifecycle order is explicit in the source manifest. The checked-out source
branch is always the final integration item and is never recreated. Stack
materialization creates only preceding cumulative branches under
`<source-worktree>/.worktrees/<sanitized-branch>`, replacing `/` with `-`.

Creation and local rebases are transactional: abort active Git operations,
restore original tips, and remove only resources created by the failed run.
Never overwrite dirty or ambiguous worktrees. Never push or perform PR work.
