"""Pre-flight check for PR-related commands.

Detects PR number from current branch or returns explicit PR info.
Call before running review-post, review-update, review-fetch.

Usage:
    uv run python .agents/scripts/preflight-pr.py [--pr <number>] [--branch <name>]

If --pr is given, validates that PR exists.
If --branch is given, finds PR for that branch.
If neither, detects from current branch.
Exits 0 with PR number on stdout, non-zero otherwise.
<EOF_DESC>
"""

import argparse
import json
import sys
from pathlib import Path

from cli_common import EXIT_EXTERNAL, ExternalCommandError, run_process

GH_SCRIPT = Path(__file__).with_name("gh.py")


def get_branch():
    return run_process(["git", "branch", "--show-current"])


def find_pr(branch: str) -> dict | None:
    out = run_process([
        sys.executable,
        str(GH_SCRIPT),
        "cmd",
        "--format",
        "raw",
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "number,headRefName,baseRefName,title,state",
    ])
    if out:
        items = json.loads(out)
        if items:
            return items[0]
    return None


def validate_pr(number: str) -> dict | None:
    out = run_process([
        sys.executable,
        str(GH_SCRIPT),
        "cmd",
        "--format",
        "raw",
        "pr",
        "view",
        number,
        "--json",
        "number,headRefName,baseRefName,title,state",
    ])
    if out:
        return json.loads(out)
    return None


def main():
    parser = argparse.ArgumentParser(description="Pre-flight check for PR-related commands")
    parser.add_argument("--pr", type=str, default=None, help="PR number to validate")
    parser.add_argument("--branch", type=str, default=None, help="Branch to find PR for")
    parser.add_argument("pr_or_url", nargs="?", help="PR number or URL to validate")
    args = parser.parse_args()
    if args.pr and args.pr_or_url:
        parser.error("provide a PR using either the positional argument or --pr")
    args.pr = args.pr or args.pr_or_url

    try:
        if args.pr:
            pr = validate_pr(args.pr)
            if pr:
                print(pr["number"])
                sys.exit(0)
            print(f"[WARN] PR #{args.pr} not found.", file=sys.stderr)
            sys.exit(1)

        branch = args.branch or get_branch()
        if not branch:
            print("[WARN] Not on a branch and no --branch provided.", file=sys.stderr)
            sys.exit(1)

        pr = find_pr(branch)
        if pr:
            print(pr["number"])
            sys.exit(0)

        print(f"[WARN] No open PR found for branch '{branch}'.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as error:
        print(f"[FAIL] GitHub returned invalid JSON: {error}", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)
    except ExternalCommandError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)


if __name__ == "__main__":
    main()
