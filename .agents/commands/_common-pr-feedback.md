# PR Feedback

Shared by commands that read or mutate PR review feedback. Read root `AGENTS.md` and load the `gh` skill. Acquire `$PR_INPUT` through `_common-review-context.md` before these commands; they and every local source path run from the returned worktree. Use `.agents/scripts/gh.py` for every PR operation.

```bash
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --output "$OUTPUT"
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --all --output "$OUTPUT"
uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/review-body.md ./tmp/review-comments.json --event "$EVENT"
uv run python .agents/scripts/gh.py interact reply "$URL" ./tmp/reply.md
uv run python .agents/scripts/gh.py interact resolve "$URL"
uv run python .agents/scripts/gh.py interact minimize "$URL" --classifier OUTDATED
```

Use active comments by default; use `--all` only for full reconciliation. Treat fetched Markdown as human input, `--urls-only` as JSON Lines, `fetch pr --format json` as JSON, and `cmd --format raw` as raw text. Preserve active human discussions. Check every remote write result and stop on failure; never fall back to raw `gh`.

Remote planning is always dry-run and needs no write flag. Applying baseline cleanup requires `/review --sync-remote`, exact repository/PR/head identity, reply-before-resolve, and actor ownership before minimizing a review body. Partial failure is nonzero and leaves the canonical report available for retry.
