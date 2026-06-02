"""Pre-flight check for rebase and commit-cleanup commands.

Checks: unique commits, already-applied duplicates, potential merge conflicts,
and uncommitted changes. Call before running /rebase or /commit-cleanup.

Usage:
    uv run python .agents/scripts/preflight-rebase.py [--target <branch>] [--list-commits] [--detect-base]

Options:
    --target <branch>     Target branch to check against (default: main)
    --list-commits        Show the full list of unique commits on this branch
    --detect-base         Detect the true parent base for stacked branches
                          (defaults to stacked rebase: find tightest ancestor)

Exits 0 if rebase is safe, non-zero with warnings otherwise.
<EOF_DESC>
"""

import subprocess, sys, argparse, json


def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError as e:
        return e.output.strip() if e.output else ""
    except Exception:
        return ""


def get_unique_commits(target: str) -> list[str]:
    """Get commits on HEAD that are not in target."""
    out = run(["git", "log", "--oneline", f"{target}..HEAD"])
    return [l for l in out.splitlines() if l.strip()] if out else []


def check_upstream_sync() -> list[str]:
    """Check if local branch is in sync with its remote tracking branch."""
    msgs = []
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    if not upstream or "@{upstream}" in upstream:
        return ["[INFO] No upstream tracking branch configured — skipping remote sync check."]

    local = run(["git", "rev-parse", "HEAD"])
    remote = run(["git", "rev-parse", "@{upstream}"])
    if not local or not remote:
        return ["[WARN] Could not resolve local or remote HEAD — skipping remote sync check."]

    if local == remote:
        return []

    behind_count = int(run(["git", "rev-list", "--count", f"HEAD..@{upstream}"]) or 0)
    ahead_count = int(run(["git", "rev-list", "--count", f"@{upstream}..HEAD"]) or 0)

    if behind_count > 0 and ahead_count > 0:
        msgs.append(f"[FAIL] Branch has diverged: {ahead_count} ahead, {behind_count} behind @{upstream}")
        msgs.append(f"       Run `git pull --rebase` first to reconcile.")
    elif behind_count > 0:
        msgs.append(f"[FAIL] Branch is {behind_count} commit(s) behind @{upstream}")
        msgs.append(f"       Run `git pull --rebase` first to catch up before rebasing.")
    elif ahead_count > 0:
        msgs.append(f"[INFO] Branch is {ahead_count} commit(s) ahead of @{upstream} (will be pushed after rebase).")

    return msgs


def check_ahead_behind(target: str) -> list[str]:
    msgs = []
    ahead = int(run(["git", "rev-list", "--count", f"{target}..HEAD"]) or 0)
    behind = int(run(["git", "rev-list", "--count", f"HEAD..{target}"]) or 0)

    if ahead == 0 and behind == 0:
        msgs.append("[INFO] Branch is already up to date — nothing to rebase.")
    elif ahead > 0:
        msgs.append(f"[INFO] {ahead} unique commit(s) on this branch (will be replayed).")
    if behind > 0:
        msgs.append(f"[INFO] {behind} commit(s) behind {target} (will be pulled in).")
    return msgs


def check_duplicates(target: str) -> list[str]:
    dupes = run(["git", "log", "--oneline", "--cherry-pick", f"{target}...HEAD"])
    if dupes:
        eq = [l for l in dupes.splitlines() if l.startswith("=")]
        if eq:
            return [f"[WARN] {len(eq)} commit(s) already in {target} (will be skipped):"] + \
                   [f"       {l[1:]}".strip() for l in eq]
    return []


def check_uncommitted() -> list[str]:
    status = run(["git", "status", "--porcelain"])
    if status:
        lines = status.splitlines()
        return [f"[WARN] {len(lines)} uncommitted file(s) (carried into rebase):"] + \
               [f"       {l}" for l in lines]
    return []


def check_potential_conflicts(target: str) -> list[str]:
    """Check for potential merge conflicts using merge-tree.

    Runs a dry three-way merge between the merge-base and each side.
    This is the most reliable pre-rebase conflict detection without actually
    running the rebase.
    """
    msgs = []
    merge_base = run(["git", "merge-base", target, "HEAD"])
    if not merge_base:
        return ["[WARN] Cannot determine merge base — skipping conflict check."]

    # Try merge-tree
    try:
        merged = subprocess.check_output(["git", "merge-tree", merge_base, target, "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["[WARN] `git merge-tree` not available (git >= 2.35 required) — skipping conflict check."]
    
    if not merged:
        return ["[INFO] No merge conflicts detected in dry run — rebase should be clean."]

    # Parse merge-tree output for conflicting files
    conflict_files = set()
    for line in merged.splitlines():
        if line.startswith("changed in both"):
            parts = line.split()
            if len(parts) >= 4:
                conflict_files.add(parts[3])
        elif "<<<<<<<" in line or "=======" in line or ">>>>>>>" in line:
            in_conflict = True

    if conflict_files:
        msgs.append(f"[WARN] {len(conflict_files)} file(s) may conflict during rebase:")
        for f in conflict_files:
            msgs.append(f"       {f}")
        msgs.append("[INFO] Run `git rebase {target}` to see exact conflicts.")
        msgs.append("[INFO] Use the question/ask tool to involve the user in conflict resolution.")
    else:
        msgs.append("[INFO] No merge conflicts detected in dry run — rebase should be clean.")

    return msgs


def list_unique_commits(target: str) -> list[str]:
    commits = get_unique_commits(target)
    if not commits:
        return ["[INFO] No unique commits on this branch."]
    result = [f"[INFO] {len(commits)} unique commit(s):"]
    for c in commits:
        result.append(f"       {c}")
    return result


def get_current_branch() -> str:
    return run(["git", "branch", "--show-current"])


def check_pr_base(branch: str) -> str | None:
    """Check if branch has an open PR on GitHub and return its base branch.

    Uses `gh pr list --head <branch> --json baseRefName` to find the PR base.
    Returns the base branch name (e.g. 'main', 'base/refactor-sdk-v2')
    or None if no open PR exists for this branch.
    """
    out = run([
        "gh", "pr", "list", "--head", branch, "--state", "open",
        "--json", "baseRefName", "--jq", ".[0].baseRefName"
    ])
    return out if out else None


def detect_base() -> str:
    """Detect the tightest parent branch (stacked base) for the current branch.

    Priority:
    1. If branch has an open PR on GitHub, use the PR's target base.
    2. Otherwise, find the local branch that is the most recent common
       ancestor (closest to HEAD) that is a proper ancestor of HEAD.
       Excludes main/master/develop and the current branch itself.

    Returns the branch name, or 'main' if none found.
    """
    branch = get_current_branch()
    if not branch or branch in ("main", "master", "develop"):
        return "main"

    # Priority 1: Check if branch has an open PR
    pr_base = check_pr_base(branch)
    if pr_base:
        return pr_base

    # Priority 2: Local ancestor detection (stacked branches)
    branches = run(["git", "branch", "--list", "--format", "%(refname:short)"])
    if not branches:
        return "main"

    best_candidate = "main"
    best_distance = 999999

    for b in branches.splitlines():
        b = b.strip().replace("* ", "")
        if b in ("main", "master", "develop", branch):
            continue
        try:
            subprocess.check_output(
                ["git", "merge-base", "--is-ancestor", b, "HEAD"],
                stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue  # b is not an ancestor of HEAD

        # b is an ancestor — get the merge-base and count distance
        mb = run(["git", "merge-base", b, "HEAD"])
        if not mb:
            continue
        count_out = run(["git", "rev-list", "--count", f"{mb}..HEAD"])
        count = int(count_out) if count_out else 999999
        b_head = run(["git", "rev-parse", b])
        b_count_out = run(["git", "rev-list", "--count", f"{mb}..{b_head}"])
        b_count = int(b_count_out) if b_count_out else 999999
        total = count + b_count

        if total < best_distance:
            best_distance = total
            best_candidate = b

    return best_candidate


def main():
    parser = argparse.ArgumentParser(description="Pre-flight check for rebase")
    parser.add_argument("--target", type=str, default="main", help="Target branch (default: main)")
    parser.add_argument("--list-commits", action="store_true", help="Show unique commits on this branch")
    parser.add_argument("--detect-base", action="store_true", help="Detect true parent base for stacked branches")
    args = parser.parse_args()

    if args.detect_base:
        branch = get_current_branch()
        base = detect_base()
        print(f"branch={branch}")
        print(f"base={base}")
        pr_base = check_pr_base(branch) if branch else None
        if pr_base:
            print(f"source=pr (target of open PR for {branch})")
        elif base not in ("main", "master", "develop", branch):
            print(f"source=local (tightest ancestor branch)")
        else:
            print(f"source=default")
        if base not in ("main", "master", "develop"):
            unique = get_unique_commits(base)
            print(f"unique_commits={len(unique)}")
            print(f"stacked=true")
        else:
            print(f"stacked=false")
        sys.exit(0)

    all_warnings = []
    all_warnings.extend(check_upstream_sync())
    all_warnings.extend(check_ahead_behind(args.target))
    all_warnings.extend(check_duplicates(args.target))
    all_warnings.extend(check_potential_conflicts(args.target))
    all_warnings.extend(check_uncommitted())

    if args.list_commits:
        all_warnings.extend(list_unique_commits(args.target))

    for w in all_warnings:
        print(w)

    critical = [w for w in all_warnings if w.startswith("[WARN]")]
    if critical:
        sys.exit(1)
    print("[OK] Rebase pre-flight checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
