---
description: Fetches all active PR comments into a local review report file
subtask: true
---

Fetch active (non-minimized, non-resolved) comments and reviews from a GitHub PR and generate a structured review report.

> Load skill: review-pr (for pulling PR comments into local review)

**Query**: $1 (natural language query — specify the PR, e.g., "fetch reviews from PR #42" or simply "42")
**Output File (Optional)**: $2 (defaults to `./reviews/remote/REVIEW_{branch}_fetched_{ts}.md`)


## Instructions

1. **Detect PR**: If `$1` is not provided, detect the PR number:
   ```bash
   PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
   ```
2. **Fetch all active comments and reviews**:
   ```bash
   uv run python .agents/scripts/gh.py fetch comments "$PR_NUMBER" --output ./tmp/fetched.md
   ```
   Read `./tmp/fetched.md` — it contains every active review grouped by author with all inline comments, each with its URL.
3. **Compile findings**: For each active inline comment, extract:
    - **Issue Code**: From the comment body (FETCH-001, FETCH-002, ...) or auto-assign
    - **Severity**: Infer from review state (CHANGES_REQUESTED → HIGH, COMMENT → MEDIUM)
    - **Location**: The file path and line number from the comment
    - **Description**: The comment body
    - **Suggested Fix**: Extract from the comment body if present
    - **How to Validate**: Extract from the comment body if present
    - **PR Comment URL**: The `URL:` line from the fetch output for this comment — preserve it as `**PR Comment**: <url>`
    - **PR Review URL**: The `URL:` line from the review header — preserve it as `**PR Review URL**: <url>`
4. **Generate report**: Write the review report to `$2` (or default path) using the REVIEW-template.md structure. Include the PR Comment URL as a field in each finding.

---

## Required Context

- Preflight: none
- Skills: review-pr, gh
- Rules: none
- Templates: REVIEW-template.md
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no (read-only fetch)
- Requires user confirmation: no

## Important

- Only active (non-minimized, non-resolved) comments are fetched by default. Use `--all` to include everything.
- Distinguish between inline comments (file-specific) and top-level review summaries (general).
- Respect review state: CHANGES_REQUESTED reviews have actionable findings; COMMENTED reviews are informational.
- If the PR has no active comments, report that and exit cleanly.
