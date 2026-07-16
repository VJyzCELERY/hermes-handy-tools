# Review Context

Shared by review commands. Read root `AGENTS.md` and load the command's review rules/skills. A PR-targeted entrypoint first normalizes its explicit or report-linked `$PR_INPUT`, then acquires that PR from the primary checkout:

```bash
PRIMARY=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
TARGET_RESULT=$(cd "$PRIMARY" && uv run python .agents/scripts/resolve-target-worktree.py "$PR_INPUT" --read-only)
```

Require a PR target and one returned worktree path, then run every source-aware preflight, report-path, diff, and local review operation from that returned worktree. Only after acquisition, derive:

```bash
BRANCH=$(git branch --show-current)
NORMALIZED_BRANCH=${BRANCH//\//_}
REVIEW_FILE="./reviews/REVIEW_${NORMALIZED_BRANCH}.md"
```

An explicit review path overrides `$REVIEW_FILE`. Run one read-only preflight form:

```bash
# New report (read-only scope check)
uv run python .agents/scripts/preflight-review.py --scope pr

# Existing report
uv run python .agents/scripts/preflight-review.py --scope pr --review-file "$REVIEW_FILE"

# Existing report before fixes
uv run python .agents/scripts/preflight-review.py --implement --review-file "$REVIEW_FILE"

# Existing report before validation
uv run python .agents/scripts/preflight-review.py --validate --review-file "$REVIEW_FILE"
```

Preflight is diagnostic only. Do not stash, reset, pull, fetch, checkout, or otherwise synchronize Git as part of preflight. If local state is behind/diverged, stop and report it. Staleness is accepted only by `/review-validate`, which owns clarification, verification, and commit-range refresh. It blocks implement/post/archive and baseline finalization.

Classify lifecycle state through `review_workflow.py status`; `review_common.py` is the sole report-schema parser. Archives live under `./reviews/archives/`.

For PR metadata consumed by automation:

```bash
PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
uv run python .agents/scripts/gh.py fetch pr "$PR_NUMBER" --json number,title,body,baseRefName,headRefName,headRefOid --format json
uv run python .agents/scripts/gh.py fetch review-state "$PR_NUMBER"
uv run python .agents/scripts/gh.py cmd --format raw pr diff "$PR_NUMBER"
```

Review files under `./reviews/` are local-only and must never be staged, committed, or pushed.
