"""Pre-flight check for review commands.

Checks scope (PR/branch/other), stale review, and unstaged changes.
In --scope pr|branch mode with --init-review, pre-generates the review file header
with Commit Range pre-filled so agents don't need to figure it out.

Usage:
    uv run python .agents/scripts/preflight-review.py [--scope pr|branch|other] [--review-file <path>] [--init-review] [--review-name <name>]
    uv run python .agents/scripts/preflight-review.py --implement [--review-file <path>]
    uv run python .agents/scripts/preflight-review.py --validate --review-file <path>

Options:
    --scope SCOPE      pr (PR context), branch (local branch), other (default)
    --review-file      Path to REVIEW_*.md file (for stale check)
    --init-review      Pre-generate review file header with Commit Range
    --review-name      Name for the review file (defaults to branch name)
    --implement        Implement preflight: auto-detect all reviews, or check a specific file
    --validate         Validation preflight: permits dirty and stale reports only

Exits 0 if all clear, non-zero with warnings.
With --init-review, also prints the review file path so the agent knows where to write.
<EOF_DESC>
"""

import argparse
import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

import repo_guard
from cli_common import EXIT_EXTERNAL, EXIT_FAILURE, ExternalCommandError, run_process

# Import check_branch_health from update-commit-range.py (hyphenated filename)
_spec = importlib.util.spec_from_file_location(
    "update_commit_range",
    repo_guard.repo_root() / ".agents" / "scripts" / "update-commit-range.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
check_branch_health = _mod.check_branch_health


_commit_base = None
GH_SCRIPT = Path(__file__).with_name("gh.py")


def resolve_review_name(name: str | None = None) -> str:
    """Normalize a review name.

    - If None or empty, default to current branch name.
    - If already starts with REVIEW_, keep as-is.
    - Otherwise prepend REVIEW_.

    Returns the normalized name only (no .md, no path).
    """
    if not name:
        name = run(["git", "branch", "--show-current"]) or "review"
    name = name.strip().replace("/", "_")
    if not name.startswith("REVIEW_"):
        name = f"REVIEW_{name}"
    return name


def resolve_review_path(review_file: str | None = None, review_name: str | None = None) -> str:
    """Resolve a review file path.

    - If review_file is given, use it as-is.
    - Otherwise, derive from review_name or branch name: ./reviews/REVIEW_{normalized_branch}.md
      where branch slashes are normalized to underscores.
    """
    if review_file:
        return review_file
    name = resolve_review_name(review_name)
    return f"./reviews/{name}.md"


def run(cmd):
    return run_process(cmd)


def check_stale(review_file: str) -> list[str]:
    warnings = []
    if not review_file:
        return warnings
    p = repo_guard.assert_inside_repo(review_file)
    if not p.exists():
        warnings.append(f"[WARN] Review file not found: {review_file}")
        return warnings
    if p.is_dir():
        warnings.append(f"[WARN] Expected a review file but got a directory: {review_file}")
        return warnings
    try:
        with p.open() as f:
            content = f.read()
        m = re.search(r'\*{0,2}Commit Range\*{0,2}:\s*`?\s*([0-9a-f]+)\s*`?\s*\.\.\.\s*`?\s*([0-9a-f]+)\s*`?', content)
        if not m:
            warnings.append("[WARN] No Commit Range in review header.")
            return warnings
        review_head = m.group(2)
        current_head = run(["git", "rev-parse", "HEAD"])
        if review_head != current_head:
            warnings.append("[WARN] Review is stale — HEAD has moved.")
            warnings.append(f"       Review was on: {review_head}")
            warnings.append(f"       Current HEAD:  {current_head}")
            for line in run(["git", "log", "--oneline", f"{review_head}..{current_head}"]).splitlines():
                warnings.append(f"       + {line}")
    except FileNotFoundError:
        warnings.append(f"[WARN] Review file not found: {review_file}")
    return warnings


def check_unstaged() -> list[str]:
    status = run(["git", "status", "--porcelain"])
    if status:
        lines = status.splitlines()
        return [f"[WARN] {len(lines)} unstaged/uncommitted file(s):"] + [
            f"       {line}" for line in lines
        ]
    return []


def scope_pr() -> list[str]:
    global _commit_base
    info = []
    branch = run(["git", "branch", "--show-current"])
    info.append(f"[INFO] Current branch: {branch}")

    pr_data = run([
        sys.executable,
        str(GH_SCRIPT),
        "cmd",
        "--format",
        "json",
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "number,headRefName,baseRefName,title",
    ])
    if not pr_data:
        info.append("[WARN] No open PR found. Falling back to branch scope.")
        return scope_branch()

    try:
        prs = json.loads(pr_data)
        if not prs:
            info.append("[WARN] No open PR found. Falling back to branch scope.")
            return scope_branch()
        pr = prs[0]
        info.append(f"[INFO] PR #{pr['number']}: {pr.get('title','')}")
        info.append(f"[INFO] PR base: {pr['baseRefName']}")
        info.append(f"[INFO] PR head: {pr['headRefName']}")

        files_out = run([
            sys.executable,
            str(GH_SCRIPT),
            "cmd",
            "--format",
            "raw",
            "pr",
            "diff",
            str(pr["number"]),
            "--name-only",
        ])
        if files_out:
            files = [f for f in files_out.splitlines() if f.strip()]
            info.append(f"[INFO] {len(files)} file(s) changed in PR:")
            for f in files[:20]:
                info.append(f"       {f}")
            if len(files) > 20:
                info.append(f"       ... and {len(files)-20} more")

        merge_base = run(["git", "merge-base", pr['baseRefName'], "HEAD"])
        if merge_base:
            _commit_base = merge_base
            info.append(f"[INFO] Diff base: {_commit_base}")
            info.append(f"[INFO] Commit Range: {_commit_base}...HEAD")
    except json.JSONDecodeError:
        info.append("[WARN] Could not parse PR data.")
    return info


def scope_branch() -> list[str]:
    global _commit_base
    info = []
    branch = run(["git", "branch", "--show-current"])
    info.append(f"[INFO] Current branch: {branch}")

    upstream = run([
        "git",
        "for-each-ref",
        "--format=%(upstream:short)",
        f"refs/heads/{branch}",
    ])
    if upstream:
        ahead = int(run(["git", "rev-list", "--count", f"{upstream}..HEAD"]) or 0)
        behind = int(run(["git", "rev-list", "--count", f"HEAD..{upstream}"]) or 0)
        if ahead or behind:
            info.append(f"[INFO] {ahead} ahead, {behind} behind {upstream}.")
    else:
        info.append("[INFO] No upstream tracking branch configured.")

    merge_base = run(["git", "merge-base", "main", "HEAD"])
    if merge_base:
        _commit_base = merge_base
        diff_files = run(["git", "diff", "--name-only", f"{merge_base}..HEAD"])
        if diff_files:
            files = [f for f in diff_files.splitlines() if f.strip()]
            info.append(f"[INFO] {len(files)} file(s) changed vs main:")
            for f in files[:20]:
                info.append(f"       {f}")
            if len(files) > 20:
                info.append(f"       ... and {len(files)-20} more")
        info.append(f"[INFO] Diff base: {_commit_base}")
        info.append(f"[INFO] Commit Range: {_commit_base}...HEAD")
    return info


def scope_other() -> list[str]:
    info = []
    branch = run(["git", "branch", "--show-current"])
    info.append(f"[INFO] Current branch: {branch}")
    info.append("[INFO] No scope specified. Use --scope pr or --scope branch for detailed scope info.")
    return info


def init_review(review_name: str, review_dir: str = "./reviews") -> str | None:
    """Generate a review file with pre-filled header from canonical template. Returns the file path or None."""
    if not _commit_base:
        return None

    head_sha = run(["git", "rev-parse", "HEAD"])
    if not head_sha:
        return None

    rev_dir = repo_guard.assert_inside_repo(review_dir)
    rev_path = repo_guard.assert_inside_repo(rev_dir / f"{review_name}.md")
    if rev_path.exists():
        raise ValueError(f"Review report already exists: {rev_path}")
    rev_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    branch = run(["git", "branch", "--show-current"])

    template_path = repo_guard.repo_root() / ".agents" / "templates" / "REVIEW-template.md"
    if not template_path.exists():
        template_path = Path(".agents/templates/REVIEW-template.md")

    template = template_path.read_text()

    replacements = {
        "__REVIEW_NAME__": review_name,
        "__REVIEW_DATE__": date_str,
        "__BRANCH_NAME__": branch or "unknown",
        "__SCOPE__": f"branch diff ({_commit_base}..HEAD)",
        "__COMMIT_BASE__": _commit_base,
        "__COMMIT_HEAD__": head_sha,
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)

    header = template + "\n\n*Generated by preflight-review.py from .agents/templates/REVIEW-template.md*\n"

    rev_path.write_text(header)
    return str(rev_path)


def parse_review_header(review_file: str) -> dict | None:
    """Parse a review file header: extract branch and commit range.

    Returns None if the file is not a valid review report.
    """
    try:
        p = repo_guard.assert_inside_repo(review_file)
        with p.open() as f:
            content = f.read()
    except FileNotFoundError:
        return None

    if not re.search(r"^# Review Report:\s*\S", content, re.MULTILINE):
        return None

    branch = re.search(r"\*{0,2}Branch\*{0,2}:\s*(\S.+|\S)", content)
    commit_range = re.search(
        r"\*{0,2}Commit Range\*{0,2}:\s*`?\s*([0-9a-f]+)\s*`?\s*"
        r"\.\.\.\s*`?\s*([0-9a-f]+)\s*`?",
        content,
    )
    if not branch or not commit_range:
        return None

    base, head = commit_range.groups()
    return {
        "branch": branch.group(1).strip(),
        "commit_range": f"{base}...{head}",
        "base": base,
        "head": head,
    }


def format_implement_output(local_reviews: list[dict], pr_reviews: list[dict],
                             has_remote: bool, pr_number: str = "") -> str:
    """Format implement preflight output.

    Only shows sections that have content. If nothing found, returns None.
    """
    has_local = bool(local_reviews)
    has_pr = bool(pr_reviews)

    if not has_local and not has_pr:
        return None

    lines = ["[INFO] === Review Implement Preflight ==="]

    if has_local:
        lines.append("")
        lines.append("Local Review Reports:")
        for r in local_reviews:
            lines.append(f"  {r['path']} - {r['status']}")
            if r.get("branch") and r.get("current_branch") and r["branch"] != r["current_branch"]:
                lines.append(f"       (branch mismatch: review on '{r['branch']}', current is '{r['current_branch']}')")

    if has_pr:
        lines.append("")
        lines.append(f"PR #{pr_number} — Unresolved Reviews:")
        for pr in pr_reviews:
            lines.append(f"  {pr['url']}")
            lines.append(f"  Fetch: `{pr['fetch_cmd']}`")
        lines.append("")
        lines.append(f"  To fetch all active: `uv run python .agents/scripts/gh.py fetch comments {pr_number}`")

    return "\n".join(lines)


def implement_preflight_autodetect() -> int:
    """Auto-detect reviews: scan ./reviews/ for REVIEW_*.md, check each."""
    current_branch = run(["git", "branch", "--show-current"])
    current_head = run(["git", "rev-parse", "HEAD"])
    reviews_dir = Path("./reviews")
    local_reviews = []
    pr_reviews = []
    pr_number = ""

    # Scan for local review files
    if reviews_dir.exists():
        for f in sorted(reviews_dir.glob("REVIEW_*.md")):
            header = parse_review_header(str(f))
            if header is None:
                local_reviews.append({
                    "path": str(f),
                    "status": "Invalid",
                    "branch": "",
                    "current_branch": current_branch,
                })
                continue
            status = "Active"
            if header["head"] and header["head"] != current_head:
                status = "Stale"
            elif header["branch"] and header["branch"] != current_branch:
                status = "Stale (branch mismatch)"
            local_reviews.append({
                "path": str(f),
                "status": status,
                "branch": header.get("branch", ""),
                "current_branch": current_branch,
            })

    # Check for open PR and fetch individual unresolved reviews
    branch = run(["git", "branch", "--show-current"])
    if branch:
        command = [
            sys.executable,
            str(GH_SCRIPT),
            "cmd",
            "--format",
            "json",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "1",
        ]
        pr_data = run(command)
        if pr_data:
            try:
                prs = json.loads(pr_data)
            except json.JSONDecodeError as error:
                raise ExternalCommandError(
                    command,
                    f"gh.py returned invalid JSON: {error}",
                    stdout=pr_data,
                ) from error
            pr_number = str(prs[0]["number"]) if prs else ""
            # Delegate to gh.py --urls-only for proper filtered comment list
            command = [sys.executable, str(GH_SCRIPT), "fetch", "comments", pr_number, "--urls-only"]
            out = run_process(command) if pr_number else ""
            if out:
                for line in out.splitlines():
                    try:
                        entry = json.loads(line)
                        url = entry.get("url", "")
                        if url:
                            pr_reviews.append({
                                "url": url,
                                "fetch_cmd": f"uv run python .agents/scripts/gh.py fetch url {url}",
                            })
                    except json.JSONDecodeError as error:
                        raise ExternalCommandError(
                            command,
                            f"gh.py returned invalid JSON: {error}",
                            stdout=out,
                        ) from error

    output = format_implement_output(local_reviews, pr_reviews, bool(pr_reviews), pr_number)
    if output is None:
        print("[INFO] NO REVIEW FOUND.")
        return 1

    print(output)

    # Warn if any local reviews are stale
    stale = [r for r in local_reviews if r["status"] != "Active"]
    if stale:
        print(f"\n[WARN] {len(stale)} review(s) are stale or have branch mismatch.")
        print("[WARN] Ask the user directly if they want to proceed or re-review first.")
        return 1
    if local_reviews:
        print("\n[OK] All local reviews are active and match current branch.")
    return 0


def implement_preflight_check_file(review_file: str) -> int:
    """Check a specific review file for staleness and branch match."""
    p = repo_guard.assert_inside_repo(review_file)
    if not p.exists():
        print(f"[ERROR] Review file not found: {review_file}", file=sys.stderr)
        return 1

    current_branch = run(["git", "branch", "--show-current"])
    current_head = run(["git", "rev-parse", "HEAD"])
    header = parse_review_header(str(p))
    if header is None:
        print(f"[ERROR] File is not a valid review report: {review_file}", file=sys.stderr)
        return 1

    print(f"[INFO] Checking review: {review_file}")
    print(f"[INFO] Current branch: {current_branch}")
    print(f"[INFO] Review branch: {header.get('branch', 'unknown')}")
    print(f"[INFO] Review commit range: {header.get('commit_range', 'unknown')}")

    warnings = []
    if header["head"] and header["head"] != current_head:
        warnings.append("[WARN] Review is stale — HEAD has moved.")
        warnings.append(f"       Review was on: {header['head']}")
        warnings.append(f"       Current HEAD:  {current_head}")
        for line in run(["git", "log", "--oneline", f"{header['head']}..{current_head}"]).splitlines():
            warnings.append(f"       + {line}")

    if header["branch"] and header["branch"] != current_branch:
        warnings.append(f"[WARN] Branch mismatch — review targets '{header['branch']}' but current branch is '{current_branch}'")

    if warnings:
        for w in warnings:
            print(w)
        print("\n[WARN] The review may not be applicable to the current state.")
        print("[WARN] Ask the user directly: are you sure you want to implement this review?")
        print("[WARN] Consider requesting a fresh review first.")
        return 1

    print("[OK] Review is up-to-date and matches current branch.")
    return 0


def validation_preflight_check_file(review_file: str) -> int:
    """Check the safe prerequisites required before validating a review."""
    path = repo_guard.assert_inside_repo(review_file)
    if not path.is_file():
        print(f"[ERROR] Review file not found: {review_file}", file=sys.stderr)
        return 1

    header = parse_review_header(str(path))
    if header is None:
        print(f"[ERROR] File is not a valid review report: {review_file}", file=sys.stderr)
        return 1

    current_branch = run(["git", "branch", "--show-current"])
    health = check_branch_health()
    if health["status"] == "detached":
        print("[ERROR] Detached HEAD; cannot validate a review report.", file=sys.stderr)
        return 1
    if health["status"] in {"behind", "diverged"}:
        print(
            f"[ERROR] Branch is {health['status']} ({health['ahead']} ahead, "
            f"{health['behind']} behind).",
            file=sys.stderr,
        )
        return 1
    if header["branch"] != current_branch:
        print(
            f"[ERROR] Branch mismatch: review targets '{header['branch']}' but "
            f"current branch is '{current_branch}'.",
            file=sys.stderr,
        )
        return 1

    print("[OK] Validation preflight passed.")
    return 0


def _main():
    parser = argparse.ArgumentParser(description="Pre-flight check for review commands")
    parser.add_argument("--scope", choices=["pr", "branch", "other"], default="other",
                        help="Scope: pr (PR), branch (local), other (default)")
    parser.add_argument("--review-file", type=str, default=None)
    parser.add_argument("--init-review", action="store_true",
                        help="Pre-generate review file header with Commit Range")
    parser.add_argument("--review-name", type=str, default=None,
                        help="Review name (defaults to branch name)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--implement",
        action="store_true",
        help="Implement preflight mode: auto-detect reviews or check a specific file",
    )
    mode.add_argument(
        "--validate",
        action="store_true",
        help="Validation preflight mode: permits dirty and stale reports",
    )

    args = parser.parse_args()

    if args.validate:
        if not args.review_file or args.init_review:
            print(
                "[ERROR] --validate requires --review-file and cannot use --init-review.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(validation_preflight_check_file(args.review_file))

    if args.implement:
        if args.review_file:
            sys.exit(implement_preflight_check_file(args.review_file))
        else:
            sys.exit(implement_preflight_autodetect())

    if args.review_file and args.init_review:
        print("[ERROR] --review-file and --init-review are mutually exclusive.", file=sys.stderr)
        print("[ERROR] Use --init-review for a NEW review (pre-generates header).", file=sys.stderr)
        print("[ERROR] Use --review-file to check an EXISTING review for staleness.", file=sys.stderr)
        print("[ERROR] Retry with only one of these flags.", file=sys.stderr)
        sys.exit(1)

    warnings = []
    info_lines = []

    if args.scope == "pr":
        info_lines.extend(scope_pr())
    elif args.scope == "branch":
        info_lines.extend(scope_branch())
    else:
        info_lines.extend(scope_other())

    if args.review_file:
        warnings.extend(check_stale(args.review_file))

    warnings.extend(check_unstaged())

    # Check branch health vs remote tracking.
    health = check_branch_health()
    if health["status"] == "behind":
        warnings.append(
            f"[WARN] Branch is behind ({health['ahead']} ahead, "
            f"{health['behind']} behind)."
        )
    elif health["status"] == "diverged":
        warnings.append(
            f"[WARN] Branch is diverged ({health['ahead']} ahead, "
            f"{health['behind']} behind)."
        )
    elif health["status"] == "detached":
        print("[INFO] Detached HEAD — proceed with caution.")
    elif health["status"] == "ahead":
        print(f"[INFO] Branch is {health['ahead']} commit(s) AHEAD of remote. Reviewing local state as latest.")

    has_warnings = bool(warnings)
    for line in info_lines:
        print(line)

    # Always output the default review path so agents know where to write
    default_review_path = resolve_review_path(args.review_file, args.review_name)
    print(f"[INFO] Default review path: {default_review_path}")

    # Check for existing review log
    branch = run(["git", "branch", "--show-current"]) or "unknown"
    branch = branch.replace("/", "_")
    log_path = Path("./reviews/log") / f"REVIEW_{branch}.md"
    if log_path.exists():
        print(f"[INFO] Review log exists: {log_path}")
        print(f"[INFO] Use --browse to view: uv run python .agents/scripts/review-log.py --browse {log_path}")
    else:
        print("[INFO] No review log yet for this branch (first cycle).")

    # Init review if requested
    if args.init_review and _commit_base and not has_warnings:
        name = resolve_review_name(args.review_name)
        rev_path = init_review(name)
        if rev_path:
            print(f"[INFO] Review file initialized: {rev_path}")
            print("[INFO] Fill in the findings section and update [fill in] placeholders.")

    if has_warnings:
        for w in warnings:
            print(w)
        sys.exit(1)
    print("[OK] Pre-flight checks passed.")
    sys.exit(0)


def main():
    try:
        _main()
    except ExternalCommandError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)
    except ValueError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(EXIT_FAILURE)


if __name__ == "__main__":
    main()
