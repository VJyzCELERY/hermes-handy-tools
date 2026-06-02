---
name: preflight
description: Run preflight checks before session start, reviews, PRs, and rebases
license: MIT
compatibility: opencode
metadata:
  type: infrastructure
---

# Skill: Preflight Scripts — Session Start, Review, PR, and Rebase Checks

## Purpose

Preflight scripts validate the environment before running commands. Always run the appropriate preflight before any major operation (review, PR creation, rebase) and at session start.

## Available Preflight Scripts

All scripts live in `.agents/scripts/` and are run via `uv run python`.

### preflight-start.py — Session Start (Required)

Run at the very beginning of every session. Detects OS and establishes the project boundary.

```bash
uv run python .agents/scripts/preflight-start.py
```

Output tells you:
- OS name, version, architecture
- Project root directory (do NOT operate outside it)
- Where to use for temp files (`./tmp/`)

### preflight-review.py — Before Any Review

Run before starting a review. Checks scope, stale reviews, and unstaged changes. Has two modes that are **mutually exclusive**:

**Mode A — New review** (`--init-review`, no `--review-file`):
```bash
uv run python .agents/scripts/preflight-review.py --scope pr --init-review --review-name "my-review"
```

**Mode B — Existing review staleness check** (`--review-file`, no `--init-review`):
```bash
uv run python .agents/scripts/preflight-review.py --scope pr --review-file ./reviews/REVIEW_foo.md
```

**Scope-only** (no init, no review file):
```bash
uv run python .agents/scripts/preflight-review.py --scope branch
```

> ⚠️ Do NOT pass both `--init-review` and `--review-file` — they conflict.

If the preflight exits non-zero, read the script's `<EOF_DESC>` to understand what's wrong:
```bash
head -20 .agents/scripts/preflight-review.py
```

### preflight-pr.py — PR Number Detection

Detect the PR number for the current branch, or validate a given PR number/URL.

```bash
# Auto-detect from current branch
PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)

# Validate a specific PR number
PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py "42")

# From a URL
PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py "https://github.com/owner/repo/pull/42")
```

Exits 0 with PR number on stdout, non-zero if not found.

### preflight-rebase.py — Rebase Safety Check

Check if a rebase will have conflicts before running it. Lists commits that will be rebased.

```bash
# Check rebasing current branch onto main
uv run python .agents/scripts/preflight-rebase.py --target main

# Check with explicit branch
uv run python .agents/scripts/preflight-rebase.py --target main --list-commits
```

Output tells you conflict status and commit list.

## General Preflight Pattern

Before any command that has a preflight script:

1. Read the command file (it tells you which preflight to run)
2. Run the preflight with appropriate flags
3. If it fails: read the script manually via `head -20 <script>` to find the `<EOF_DESC>` usage block
4. Fix the issue, re-run preflight, then proceed

## Common Pitfalls

- **Always use `uv run`** — never bare `python` for preflight scripts
- **Run preflight from repo root** — scripts expect to be at the project root
- **Read `<EOF_DESC>`** if a preflight fails — the usage block is right after this marker
- **Don't skip preflights** — they catch stale reviews, wrong scope, and merge conflicts before they waste time
- **`--init-review` creates the file** but does NOT fill in findings — you still need to write those
