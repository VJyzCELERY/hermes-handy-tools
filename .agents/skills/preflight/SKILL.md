---
name: preflight
description: Run read-only environment, review, PR, and rebase checks
license: MIT
compatibility: opencode
metadata:
  type: infrastructure
---

# Preflight

Preflights diagnose state; they never synchronize Git or repair failures.

```bash
uv run python .agents/scripts/preflight-start.py
uv run python .agents/scripts/preflight-review.py --scope pr
uv run python .agents/scripts/preflight-review.py --scope pr --review-file <path>
uv run python .agents/scripts/preflight-review.py --implement --review-file <path>
uv run python .agents/scripts/preflight-pr.py [pr-or-url]
uv run python .agents/scripts/preflight-rebase.py --target <branch>
```

Run the form named by the command. Stop on nonzero status and report the diagnostic. Behind/diverged state is never permission to pull, stash, reset, or rewrite history.
