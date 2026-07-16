---
name: gh
description: GitHub issue, PR, and review operations through gh.py
license: MIT
compatibility: opencode
metadata:
  type: infrastructure
---

# GitHub Operations

Use `.agents/scripts/gh.py` for every GitHub issue, PR, and review operation. Use `gh.py cmd` when no dedicated subcommand exists; never invoke raw `gh` directly.

```bash
uv run python .agents/scripts/gh.py --help
uv run python .agents/scripts/gh.py fetch issue <issue> --format json
uv run python .agents/scripts/gh.py fetch issues --state open --format json
uv run python .agents/scripts/gh.py create-issue <title> <body.md> --label <labels> --format json
uv run python .agents/scripts/gh.py claim <issue-or-pr-number> --format json
uv run python .agents/scripts/gh.py fetch pr <pr> --format json
uv run python .agents/scripts/gh.py cmd --format raw pr diff <pr>
uv run python .agents/scripts/gh.py fetch comments <pr> [--all] [--output <path>]
uv run python .agents/scripts/gh.py post review <pr> <body.md> [comments.json] --event <event>
uv run python .agents/scripts/gh.py interact reply <url> <body.md>
uv run python .agents/scripts/gh.py interact resolve <url>
uv run python .agents/scripts/gh.py interact minimize <url> --classifier OUTDATED
```

- Request `--format json` for structured metadata and `--format raw` for diffs or passthrough output.
- Put generated payloads in `./tmp/`; caller-owned files are not temporary.
- Check every exit status. Never treat failed or malformed fetches as empty results.
- Preserve active human discussions when resolving or minimizing feedback.
- `/issue` creates unclaimed issues. New PRs include the authenticated login as an assignee and start as drafts; metadata updates preserve existing readiness.
