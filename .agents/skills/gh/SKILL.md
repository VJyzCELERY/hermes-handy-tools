---
name: gh
description: GitHub PR management and review operations via gh.py
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: gh — GitHub PR and Review Operations

## Purpose

Manage GitHub PRs and reviews. All write operations go through `.agents/scripts/gh.py`. Only use `gh.py cmd api` as fallback.

## Golden Rule: Use gh.py for ALL PR Operations

**Always prefer `.agents/scripts/gh.py` — even for read operations.** Only use raw `gh` CLI when gh.py doesn't support the operation you need.

```bash
# See all available subcommands
uv run python .agents/scripts/gh.py --help
```

Temp files go in `./tmp/` (gitignored). gh.py auto-cleans on success.

## Common Operations

### Fetch

`fetch comments` returns only active (non-minimized, non-resolved) comments and reviews by default. Use `--all` to include everything:

```bash
uv run python .agents/scripts/gh.py fetch pr "$PR_NUMBER"                 # PR details (JSON)
uv run python .agents/scripts/gh.py fetch prs                              # List PRs (--head, --state, --base, --limit)
uv run python .agents/scripts/gh.py fetch repo                             # Repo info (owner, language, visibility)
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER"            # Only active (default)
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --all      # Everything including minimized
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --output ./tmp/file.md  # Write to file
```

### Post review
```bash
uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/body.md ./tmp/comments.json --event REQUEST_CHANGES
uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/body.md --event APPROVE
uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/body.md --event COMMENT
```

### Reply, resolve, minimize, unminimize (by URL)

```bash
# All of these accept a full GitHub URL and auto-detect the type (inline vs review body)
uv run python .agents/scripts/gh.py interact reply "$URL" ./tmp/reply.md
uv run python .agents/scripts/gh.py interact resolve "$URL"
uv run python .agents/scripts/gh.py interact minimize "$URL" --classifier OUTDATED
uv run python .agents/scripts/gh.py interact unminimize "$URL"
```

### Post inline comment
```bash
uv run python .agents/scripts/gh.py post inline "$PR_NUMBER" ./tmp/inline.md --path src/file.py --line 42
```

### Update
```bash
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER"         # Active comments/reviews
uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --all   # All including minimized
```

### Create PR
1. Read `.agents/templates/PR-body.md` and fill in all sections based on the spec/design/changes
2. Write the filled body to `./tmp/pr-body.md`
3. Create:
```bash
uv run python .agents/scripts/gh.py create "Title" ./tmp/pr-body.md [--head <branch>] [--base <branch>]
```
4. Verify body was set: `uv run python .agents/scripts/gh.py fetch pr <pr-number>`

### Run any gh command (wildcard)
```bash
# Auto-formats JSON output to markdown, raw output passthrough for non-JSON
uv run python .agents/scripts/gh.py cmd pr view 10 --json number,title,state
uv run python .agents/scripts/gh.py cmd pr diff 10
uv run python .agents/scripts/gh.py cmd pr list --head my-branch
uv run python .agents/scripts/gh.py cmd repo view --json name,description
```

## Common Pitfalls
- **Always use gh.py first** — even for read operations. Only fall back to raw `gh` CLI if gh.py doesn't have the subcommand
- **Retry on transient/syntax errors** — if gh.py fails with a syntax/transient error, retry once after a 2-second pause before falling back to raw `gh`
- **Check gh.py --help** before using raw `gh` — the operation you need may already be covered
- **Use `gh.py cmd` for all `gh` operations** — e.g., `uv run python .agents/scripts/gh.py cmd pr diff "$PR_NUMBER"` instead of the equivalent raw `gh` command
- **Unknown commands** — run `uv run python .agents/scripts/gh.py cmd ...` to pass through any `gh` operation
- **`side: "RIGHT"`** for new version, **`side: "LEFT"`** for old version
- **Validate JSON** before posting: `cat ./tmp/file.json | uv run python -m json.tool`
- Write temp files under `./tmp/` — it's gitignored
