Standard pre-flight invocation for review commands. Sets `REVIEW_FILE` for use by subsequent steps.

Run preflight to detect the review file and check for staleness:

```bash
# Auto-detect the review file (checks ./reviews/ for REVIEW_*.md)
REVIEW_FILE=$(ls ./reviews/REVIEW_*.md 2>/dev/null | head -1)
if [ -z "$REVIEW_FILE" ]; then
  BRANCH=$(git branch --show-current | tr '/' '-')
  echo "[INFO] No review file found in ./reviews/."
  echo "       Default path would be: ./reviews/REVIEW_${BRANCH}.md"
fi
```

Then invoke the preflight:

```bash
uv run python .agents/scripts/preflight-review.py --scope pr --review-file "$REVIEW_FILE"
```

- If preflight exits non-zero, read its warnings: staleness, unstaged changes, scope problems.
- If `$REVIEW_FILE` is empty, the preflight shows the default path in its output.
- Default review path: `./reviews/REVIEW_{branch}.md` (branch slashes → `-`).
- Common variants: `REVIEW_{branch}_refreshed.md`, `REVIEW_{branch}_fetched_*.md`.
- Always load this module before running any review command.
