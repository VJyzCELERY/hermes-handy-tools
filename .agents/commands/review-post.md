---
description: Posts a review report as a PR review with inline comments and tracks URLs
subtask: true
---

Post a completed review report as a GitHub PR review with inline comments. After posting, update the local review report with the URLs of each posted comment.

> Load skill: review-pr (for posting reviews as PR inline comments)

**Query**: $1 (natural language query or review file path, e.g., "post the review from reviews/REVIEW_foo.md to PR #42" or simply "reviews/REVIEW_foo.md")
**PR Number (Optional)**: $2 (if not provided, detect from current branch or parse from query)

---

## Overview

This command reads a review report from `$1`, extracts each finding, and posts them as a structured PR review with inline comments. All findings are listed in the review body — inline findings link to diff lines, non-inline findings include full details. After posting, it updates the local review report to track the URL of each comment so future commands (verify, clarify) can reply and resolve them automatically.

---

## Instructions

> Load _common-preflight.md
> Load skill: gh (for gh.py — all posting operations)

1. **Read the review report**: Load the REVIEW_{name}.md file
2. **Detect PR**: If `$2` is not provided, detect the PR number:
   ```bash
   PR_NUMBER=$(uv run python .agents/scripts/preflight-pr.py)
   ```
3. **Get PR diff**: Download the PR diff to map line numbers:
   ```bash
     uv run python .agents/scripts/gh.py cmd pr diff "$PR_NUMBER"
   ```
 4. **Read Overall Assessment**: Extract the `**Overall Assessment**` field from the review report header. This determines the PR review event and the emote.
 5. **Get commit range**: Determine the commit range reviewed:
    ```bash
    BASE_SHA=$(uv run python .agents/scripts/gh.py cmd pr view "$PR_NUMBER" --json baseRefOid --jq .baseRefOid)
    HEAD_SHA=$(uv run python .agents/scripts/gh.py cmd pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
    ```
   6. **Classify findings**: For each finding, try to map the **Location** to the current diff:
      - **Inline-capable (OPEN only)**: finding status is OPEN **and** has a valid `file:line` that exists in the current diff → will be posted as an inline comment
      - **Non-inline or ADDRESSED**: finding status is ADDRESSED **or** targets PR metadata (title, body, etc.) **or** the line no longer exists in the diff → full details MUST be preserved in the review body findings section (no inline comment)
  7. **Build inline comments**: For each inline-capable finding, build an inline comment with `path`, `line`, `side`, and `body`. Every `body` field and the entire review body is **markdown** — use fenced code blocks for commands, bullet lists, bold, etc. Issue IDs should follow `{TEXT}-{NUMBER}` format (e.g. `F-001`, `MED-001`, `ISSUE-001`) — keep them short and consistent within this review. The inline body MUST start with `**[<issue-id>]** - **[<priority>]** - <short description>` (e.g., `**F-001** - **HIGH** - Serialization Plan Reuses Non-Serializable Agent Config`).
  8. **Post the review** with a single review body and inline comments:
     - Build the review body using `.agents/templates/review-body-snippet.md`
      - The body lists ALL findings — OPEN inline-able findings are marked "Details inline" (full details in the separate inline comment); ADDRESSED findings include **Status**: ✅ Addressed / **Resolution**: <what was done> and full Why/Suggestion/How to Validate; non-inline findings include full Why/Suggestion/How to Validate directly in the body
     - Post everything in one go with all inline comments and the body

    ```bash
     REVIEW_FILE="$1"
     REVIEW_EVENT="APPROVE"  # default
     if grep -q "Change Requested\|Blocked" "$REVIEW_FILE"; then
       REVIEW_EVENT="REQUEST_CHANGES"
     elif grep -q "Approved With Recommendation" "$REVIEW_FILE"; then
       REVIEW_EVENT="APPROVE"
     fi

     # Map assessment to emote
      ASSESSMENT=$(grep -oP '\*\*Overall Assessment\*\*:\s*\K.*' "$REVIEW_FILE" | head -1)
      case "$ASSESSMENT" in
        *Approved*) EMOTE="✅" ;;
        *Addressed With Potential Follow-up*) EMOTE="✅" ;;
        *Change Requested*) EMOTE="⚠️" ;;
        *Blocked*) EMOTE="❌" ;;
        *) EMOTE="" ;;
      esac

     # --- Main review: inline comments + body ---
     # Copy the template, then edit placeholders in place.
     # IMPORTANT: The review body is markdown. Use proper markdown formatting (fenced code blocks, lists, bold, etc.)
     cp .agents/templates/review-body-snippet.md ./tmp/review-body.md
     # Then edit ./tmp/review-body.md to replace placeholders with actual values.
     
     # Build inline comments JSON — copy template, then replace placeholders
     cp .agents/templates/inline-comment-format.json ./tmp/review-comments.json
     # Then edit ./tmp/review-comments.json to replace placeholders.
     # For the body field, use the content from .agents/templates/inline-comment-body-snippet.md
     # and escape it as a JSON string (replace \n with \\n, escape quotes).
     
      uv run python .agents/scripts/gh.py post review "$PR_NUMBER" ./tmp/review-body.md ./tmp/review-comments.json --event "$REVIEW_EVENT"
      ```
  9. **Capture URLs from post review output**: The `gh.py post review` command now outputs the review URL and each inline comment URL directly. Capture them:
    - The `Review URL:` line → add as `**PR Review URL**` in the report header
    - The `Comment URL:` lines → add as `**PR Comment**: <url>` for each matching finding
10. **Update the local review report**: For each finding that was posted, append a `**PR Comment**` field:
   ```
   **PR Comment**: https://github.com/owner/repo/pull/<number>#discussion_r<comment-id>
   ```
   Also add a `**PR Review**` field for the overall review:
   ```
   **PR Review URL**: https://github.com/owner/repo/pull/<number>#pullrequestreview-<review-id>
   ```
   Save the updated review report. This links every finding to its PR comment so future commands can reply and resolve automatically.

---

## Inline Comment Format

Use `.agents/templates/inline-comment-format.json` for the JSON structure and `.agents/templates/inline-comment-body-snippet.md` for the body content. The `body` field must be escaped as a JSON string (replace `\n` with actual newlines, escape quotes).

> **Important**: The entire review body and all inline comment bodies are **markdown**. Use proper markdown formatting throughout — fenced code blocks for commands, bullet lists, bold/italic as appropriate. Issue IDs use `{TEXT}-{NUMBER}` format (e.g. `F-001`, `MED-001`) and must be unique within the review.

## Overall Assessment to Review Event Mapping

| Overall Assessment | Emote | Review Event |
|-------------------|-------|--------------|
| Approved | ✅ | `APPROVE` |
| Approved With Recommendation | ✅ | `APPROVE` (with inline comment notes) |
| Addressed With Potential Follow-up | ✅ | `APPROVE` (all issues closed, may revisit) |
| Change Requested | ⚠️ | `REQUEST_CHANGES` |
| Blocked | ❌ | `REQUEST_CHANGES` |

The assessment is read from the `**Overall Assessment**` field in the review report header. Include the emote in the assessment line: `**Assessment**: ✅ **Approved**`

## Required Context

- Preflight: preflight-review.py
- Skills: review-pr, gh
- Rules: none
- Templates: review-body-snippet.md, inline-comment-format.json, inline-comment-body-snippet.md
- Mutates files: yes
- Mutates git history: no
- Mutates remote: yes
- Requires user confirmation: no

## Important

- Read `.agents/scripts/gh.py` usage before posting — all PR writes go through it
- Always verify line numbers against the current PR diff before posting
- **After posting, MUST update the local review report** with PR comment URLs — this enables automatic reply/resolve in review-update
- Do NOT post reviews with empty inline comments — skip findings that can't be mapped to the diff
- **Use markdown hyperlinks when referencing other reviews or comments** — never raw IDs like `PRR_abc123`. Format: `[Previous review](https://github.com/.../pull/N#pullrequestreview-XXX) has been superseded by this review.`
- **Every How to Validate must include expected output** when the finding is addressed. Format: validation command in a code block, followed by `# Expected output (when addressed): <result>` so reviewers can confirm fixes at a glance.
