"""Update the **Commit Range** line in a review report to the current HEAD.

Usage:
    uv run python .agents/scripts/update-commit-range.py <path/to/review-file.md>

Determines the correct HEAD SHA by checking local vs remote tracking branch:
  - If local is AHEAD of remote (or equal): uses local HEAD (healthy).
  - If local is BEHIND remote (alone or diverged): marks as stale — exits with error.
    The review report is outdated and needs re-validation.

Also exports `check_branch_health()` for reuse in other scripts.
<EOF_DESC>
"""

import re
import sys
import subprocess
from pathlib import Path

import repo_guard


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def check_branch_health() -> dict:
    """Check the current branch's health vs its remote tracking branch.

    Returns:
        dict with keys:
            status: 'ahead' | 'behind' | 'diverged' | 'up_to_date' | 'no_remote' | 'detached'
            ahead: int (commits ahead of remote)
            behind: int (commits behind remote)
            head: str (local HEAD SHA)
            branch: str (current branch name)
    """
    branch = run(["git", "branch", "--show-current"])
    if not branch:
        return {"status": "detached", "ahead": 0, "behind": 0,
                "head": run(["git", "rev-parse", "HEAD"]), "branch": ""}

    head = run(["git", "rev-parse", "HEAD"])

    # Check if remote tracking exists
    remote_ref = run(["git", "rev-parse", "--abbrev-ref", "@{u}"])
    if not remote_ref:
        return {"status": "no_remote", "ahead": 0, "behind": 0,
                "head": head, "branch": branch}

    ahead_str = run(["git", "rev-list", "--count", "@{u}..HEAD"])
    behind_str = run(["git", "rev-list", "--count", "HEAD..@{u}"])
    ahead = int(ahead_str) if ahead_str else 0
    behind = int(behind_str) if behind_str else 0

    if ahead > 0 and behind > 0:
        status = "diverged"
    elif ahead > 0:
        status = "ahead"
    elif behind > 0:
        status = "behind"
    else:
        status = "up_to_date"

    return {"status": status, "ahead": ahead, "behind": behind,
            "head": head, "branch": branch}


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python .agents/scripts/update-commit-range.py <review-file.md>", file=sys.stderr)
        sys.exit(1)

    file_path = repo_guard.assert_inside_repo(sys.argv[1])
    if not file_path.exists():
        print(f"[FAIL] File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")

    # --- Step 1: Check branch health ---
    health = check_branch_health()

    if health["status"] == "detached":
        print("[FAIL] Detached HEAD — cannot determine branch health.", file=sys.stderr)
        sys.exit(1)

    if health["status"] == "no_remote":
        print("[WARN] No remote tracking branch. Using local HEAD as-is.", file=sys.stderr)

    if health["status"] == "behind":
        print(f"[WARN] Local branch is {health['behind']} commit(s) BEHIND remote.", file=sys.stderr)
        print(f"[WARN] Remote has moved ahead. Consider pulling latest changes.", file=sys.stderr)

    if health["status"] == "diverged":
        print(f"[WARN] Branch is DIVERGED — {health['ahead']} ahead, {health['behind']} behind remote.", file=sys.stderr)
        print(f"[WARN] Remote has moved (possibly rebased). Consider rebasing to resolve.", file=sys.stderr)

    # --- Step 2: Determine HEAD ---
    # If local is ahead or up-to-date, use local HEAD
    head_sha = health["head"]

    # --- Step 3: Determine base SHA ---
    # Try PR base first, else fall back to merge-base with main
    pr_number = run(["gh", "pr", "view", "--json", "number", "--jq", ".number"])
    base_sha = ""
    if pr_number:
        owner_repo = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
        if owner_repo:
            base_sha = run(["gh", "api", f"repos/{owner_repo}/pulls/{pr_number}", "--jq", ".base.sha"])

    if not base_sha:
        # Fallback: use merge-base with main
        base_sha = run(["git", "merge-base", "main", "HEAD"])

    if not base_sha:
        print("[FAIL] Could not determine base SHA (no PR and no merge-base with main).", file=sys.stderr)
        sys.exit(1)

    if not re.match(r'^[0-9a-f]{40}$', head_sha) or not re.match(r'^[0-9a-f]{40}$', base_sha):
        print(f"[FAIL] SHAs are not full 40-char hex: base={base_sha} head={head_sha}", file=sys.stderr)
        sys.exit(1)

    new_range = f"{base_sha}...{head_sha}"

    # --- Step 4: Update the review file ---
    existing = re.search(r'^\*\*Commit Range\*\*:\s*(\S+)', content, re.MULTILINE)
    if existing and existing.group(1) == new_range:
        if health["status"] == "ahead":
            print(f"[OK] Commit Range already up to date (local ahead by {health['ahead']}): {new_range}")
        else:
            print(f"[OK] Commit Range already up to date: {new_range}")
        sys.exit(0)

    # Remove all existing **Commit Range** lines (handles duplicates)
    cleaned = re.sub(r'^\*\*Commit Range\*\*:\s*\S+\s*\n?', '', content, flags=re.MULTILINE)

    # Find the right insertion point — after **Reviewer**, **Review Focus**, **Review Date**, or **Review Type**
    inserted = re.sub(
        r'^(\*\*Review(?:er|Focus| Date| Type).*\n)',
        f'\\1**Commit Range**: {new_range}\n',
        cleaned,
        count=1,
        flags=re.MULTILINE,
    )

    if inserted == cleaned:
        # Fallback: insert at the top, after the title
        inserted = re.sub(
            r'^(# .*\n)',
            f'\\1**Commit Range**: {new_range}\n',
            cleaned,
            count=1,
        )

    if inserted == cleaned:
        print("[FAIL] Could not find a place to insert Commit Range", file=sys.stderr)
        sys.exit(1)

    file_path.write_text(inserted, encoding="utf-8")

    if health["status"] == "ahead":
        print(f"[OK] Commit Range updated to local HEAD (ahead by {health['ahead']}): {new_range} in {file_path}")
    else:
        print(f"[OK] Commit Range updated to {new_range} in {file_path}")


if __name__ == "__main__":
    main()
