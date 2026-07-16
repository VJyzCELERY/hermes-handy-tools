# Common Branch Context

Load the source lifecycle manifest from `.agents/local/state/lifecycles/<id>.json`.
The source manifest owns lifecycle order and slice metadata. Each nested
worktree's `.agents/local/state/branch.json` contains only its branch,
lifecycle ID, source worktree, and worktree path.

Require a clean tree before mutation; lifecycle-owned `.agents/local/` state and
artifact files and `.worktrees/` paths are allowed. Stop on detached HEAD, malformed
state, ambiguous refs, missing worktrees, or unexpected existing resources.
These commands never push and never create or update pull requests.
