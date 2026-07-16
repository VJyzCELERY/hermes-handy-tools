"""Plan and maintain local cumulative branch lifecycles."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import branch_state
import cli_common
import repo_guard

PLAN_VERSION = 1


def git(*args: str, cwd: Path) -> str:
    """Run Git in a guarded repository path."""
    return cli_common.run_process(["git", *args], cwd=cwd)


def _root() -> Path:
    return repo_guard.assert_inside_repo(Path.cwd())


def _dirty(root: Path) -> bool:
    status = git("status", "--porcelain", "--untracked-files=all", cwd=root)
    return any(
        not line[3:].lstrip('"').startswith((".agents/local/", ".worktrees/"))
        for line in status.splitlines()
    )


def _clean(root: Path) -> None:
    if _dirty(root):
        raise ValueError("Source worktree must be clean")


def _branch(root: Path) -> str:
    branch = git("branch", "--show-current", cwd=root)
    if not branch:
        raise ValueError("Detached HEAD is not supported")
    return branch


def _valid_ref(root: Path, ref: str) -> None:
    git("check-ref-format", "--branch", ref, cwd=root)


def _parse_slice(value: str) -> tuple[str, int]:
    try:
        branch, count = value.rsplit("=", 1)
        parsed = int(count)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError("slice must be BRANCH=COMMIT_COUNT") from error
    if not branch or parsed < 1:
        raise argparse.ArgumentTypeError("slice must be BRANCH=COMMIT_COUNT")
    return branch, parsed


def _breakdown_plan(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    source = _branch(root)
    _valid_ref(root, args.base)
    if not args.slices:
        raise ValueError("At least one --slice is required")
    if git("rev-list", "--min-parents=2", f"{args.base}..HEAD", cwd=root):
        raise ValueError("Breakdown requires a linear, merge-free commit history")
    commits = git("rev-list", "--reverse", f"{args.base}..HEAD", cwd=root).splitlines()
    if sum(count for _, count in args.slices) != len(commits):
        raise ValueError("Slice commit counts must exactly cover base..HEAD")
    if args.slices[-1][0] != source:
        raise ValueError("The source branch must be the final integration slice")
    slices = []
    offset = 0
    for order, (name, count) in enumerate(args.slices, 1):
        _valid_ref(root, name)
        selected = commits[offset : offset + count]
        previous = args.base if order == 1 else args.slices[order - 2][0]
        paths = sorted(
            set(
                git("diff-tree", "--no-commit-id", "--name-only", "-r", oid, cwd=root)
                for oid in selected
            )
        )
        paths = sorted({path for group in paths for path in group.splitlines() if path})
        numstat = git("diff", "--numstat", f"{selected[0]}^", selected[-1], cwd=root)
        changed = sum(
            int(value)
            for line in numstat.splitlines()
            for value in line.split("\t")[:2]
            if value.isdigit()
        )
        title = git("show", "-s", "--format=%s", selected[-1], cwd=root)
        slices.append(
            {
                "order": order,
                "id": f"slice-{order}",
                "branch": name,
                "title": title,
                "purpose": title,
                "paths": paths,
                "intended_base": previous,
                "rationale": "Separate approved commit boundary.",
                "dependencies": [] if order == 1 else [f"slice-{order - 1}"],
                "changed_lines": {"total": changed, "review_budget": changed},
                "validation": {
                    "command": "deferred to approved plan",
                    "status": "deferred",
                    "reason": "Planning output requires reviewer selection.",
                },
                "review_disposition": "required",
                "skip_reason": None,
                "commits": selected,
                "boundary": {
                    "first": selected[0],
                    "last": selected[-1],
                    "count": len(selected),
                },
                "tree": git("rev-parse", f"{selected[-1]}^{{tree}}", cwd=root),
            }
        )
        offset += count
    return {
        "version": PLAN_VERSION,
        "operation": "breakdown",
        "lifecycle_id": args.lifecycle_id,
        "issue_id": args.issue_id,
        "source_branch": source,
        "base_branch": args.base,
        "base_head": git("rev-parse", args.base, cwd=root),
        "source_head": git("rev-parse", "HEAD", cwd=root),
        "source_tree": git("rev-parse", "HEAD^{tree}", cwd=root),
        "diff_summary": {
            "changed_files": len(
                git("diff", "--name-only", f"{args.base}...HEAD", cwd=root).splitlines()
            ),
            "total_changed_lines": sum(
                item["changed_lines"]["total"] for item in slices
            ),
            "review_budget_lines": sum(
                item["changed_lines"]["review_budget"] for item in slices
            ),
        },
        "slices": slices,
        "approved": False,
    }


def _validate_plan(value: Any) -> dict[str, Any]:
    keys = {
        "version",
        "operation",
        "lifecycle_id",
        "issue_id",
        "source_branch",
        "base_branch",
        "base_head",
        "source_head",
        "source_tree",
        "diff_summary",
        "slices",
        "approved",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Approved plan has an invalid schema")
    if value["version"] != PLAN_VERSION or value["operation"] != "breakdown":
        raise ValueError("Approved plan version or operation is unsupported")
    manifest = {
        "version": branch_state.VERSION,
        "id": value["lifecycle_id"],
        "issue_id": value["issue_id"],
        "source_branch": value["source_branch"],
        "base_branch": value["base_branch"],
        "base_head": value["base_head"],
        "source_head": value["source_head"],
        "source_tree": value["source_tree"],
        "slices": value["slices"],
    }
    branch_state.validate_lifecycle(manifest)
    if value["approved"] is not True:
        raise ValueError("Plan must contain explicit approved=true")
    return value


def _read_plan(path: Path, root: Path) -> dict[str, Any]:
    path = repo_guard.assert_inside_repo(path if path.is_absolute() else root / path)
    try:
        return _validate_plan(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read approved plan: {error}") from error


def _apply_breakdown(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    _clean(root)
    if _branch(root) != plan["source_branch"]:
        raise ValueError("Approved plan source branch is not checked out")
    if git("rev-parse", "HEAD", cwd=root) != plan["source_head"]:
        raise ValueError("Approved plan is stale: source HEAD changed")
    if git("rev-parse", "HEAD^{tree}", cwd=root) != plan["source_tree"]:
        raise ValueError("Approved plan is stale: source tree changed")
    current = git("rev-list", "--reverse", f"{plan['base_branch']}..HEAD", cwd=root)
    planned = [oid for item in plan["slices"] for oid in item["commits"]]
    if current.splitlines() != planned:
        raise ValueError("Approved plan is stale: commit range changed")

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    safe_source = re.sub(r"[^A-Za-z0-9._-]", "_", plan["source_branch"])
    backup = f"backup/{safe_source}-{stamp}"
    git("branch", backup, plan["source_head"], cwd=root)
    try:
        git("reset", "--hard", plan["base_branch"], cwd=root)
        rebuilt = []
        for item in plan["slices"]:
            new_commits = []
            for oid in item["commits"]:
                git("cherry-pick", oid, cwd=root)
                new_commits.append(git("rev-parse", "HEAD", cwd=root))
            rebuilt.append(
                {
                    **item,
                    "commits": new_commits,
                    "boundary": {
                        "first": new_commits[0],
                        "last": new_commits[-1],
                        "count": len(new_commits),
                    },
                    "tree": git("rev-parse", "HEAD^{tree}", cwd=root),
                }
            )
        if git("rev-parse", "HEAD^{tree}", cwd=root) != plan["source_tree"]:
            raise RuntimeError(
                "Rebuilt source tree does not match the approved final tree"
            )
    except Exception:
        try:
            git("cherry-pick", "--abort", cwd=root)
        except cli_common.ExternalCommandError:
            pass
        git("reset", "--hard", backup, cwd=root)
        raise

    manifest = {
        "version": branch_state.VERSION,
        "id": plan["lifecycle_id"],
        "issue_id": plan["issue_id"],
        "source_branch": plan["source_branch"],
        "base_branch": plan["base_branch"],
        "base_head": plan["base_head"],
        "source_head": git("rev-parse", "HEAD", cwd=root),
        "source_tree": plan["source_tree"],
        "slices": rebuilt,
    }
    try:
        branch_state.write_lifecycle(root, manifest)
    except Exception:
        git("reset", "--hard", backup, cwd=root)
        raise
    return {"status": "applied", "backup_branch": backup, "manifest": manifest}


def breakdown(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Plan or apply a source branch breakdown."""
    if args.apply_plan:
        return _apply_breakdown(_read_plan(args.apply_plan, root), root)
    return _breakdown_plan(args, root)


def _stack_plan(root: Path, lifecycle_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = branch_state.read_lifecycle(root, lifecycle_id)
    source = root.resolve()
    worktrees_root = source / ".worktrees"
    items = []
    parent = manifest["base_branch"]
    for item in manifest["slices"][:-1]:
        path = worktrees_root / item["branch"].replace("/", "-")
        items.append(
            {
                "order": item["order"],
                "branch": item["branch"],
                "base_branch": parent,
                "start": item["commits"][-1],
                "worktree": str(path),
            }
        )
        parent = item["branch"]
    return manifest, {
        "operation": "stack",
        "lifecycle_id": lifecycle_id,
        "items": items,
    }


def _remove_worktree(root: Path, path: Path) -> None:
    try:
        git("worktree", "remove", "--force", str(path), cwd=root)
    except cli_common.ExternalCommandError:
        pass


def stack(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Preview or materialize cumulative branch worktrees."""
    _clean(root)
    manifest, plan = _stack_plan(root, args.lifecycle_id)
    if not args.apply:
        return plan
    if _branch(root) != manifest["source_branch"]:
        raise ValueError("Stack must run from the checked-out source branch")
    if git("rev-parse", "HEAD", cwd=root) != manifest["source_head"]:
        raise ValueError("Stack source HEAD does not match the lifecycle manifest")
    if git("rev-parse", "HEAD^{tree}", cwd=root) != manifest["source_tree"]:
        raise ValueError("Stack source tree does not match the lifecycle manifest")
    created: list[tuple[str, Path]] = []
    try:
        for item in plan["items"]:
            branch = item["branch"]
            path = repo_guard.assert_inside_repo(item["worktree"])
            if path.exists() or git("branch", "--list", branch, cwd=root):
                raise ValueError(f"Stack resource already exists for {branch}")
            path.parent.mkdir(parents=True, exist_ok=True)
            git("worktree", "add", "-b", branch, str(path), item["start"], cwd=root)
            created.append((branch, path))
            branch_state.write_branch_state(
                path,
                {
                    "version": branch_state.VERSION,
                    "lifecycle_id": args.lifecycle_id,
                    "branch": branch,
                    "source_worktree": str(root.resolve()),
                    "worktree": str(path.resolve()),
                },
            )
    except Exception:
        for branch, path in reversed(created):
            _remove_worktree(root, path)
            try:
                git("branch", "-D", branch, cwd=root)
            except cli_common.ExternalCommandError:
                pass
        raise
    return {**plan, "status": "applied"}


def _has_remote(root: Path) -> bool:
    return bool(git("remote", cwd=root))


def _sync_status(root: Path, branch: str) -> str:
    """Classify a local branch against its configured remote branch."""
    try:
        remote = git("config", "--get", f"branch.{branch}.remote", cwd=root)
        merge = git("config", "--get", f"branch.{branch}.merge", cwd=root)
    except cli_common.ExternalCommandError:
        return "fresh"
    if not remote or not merge:
        return "fresh"
    remote_ref = f"refs/remotes/{remote}/{merge.removeprefix('refs/heads/')}"
    try:
        git("show-ref", "--verify", remote_ref, cwd=root)
    except cli_common.ExternalCommandError:
        return "missing-remote"
    ahead, behind = (
        int(value)
        for value in git(
            "rev-list", "--left-right", "--count", f"{branch}...{remote_ref}", cwd=root
        ).split()
    )
    if ahead and behind:
        return "diverged"
    if ahead:
        return "local-ahead"
    if behind:
        return "remote-ahead"
    return "fresh"


def _local_status(root: Path, item: dict[str, Any]) -> str:
    try:
        tip = git("rev-parse", item["branch"], cwd=root)
    except cli_common.ExternalCommandError:
        return "local-drift"
    return "fresh" if tip == item["commits"][-1] else "local-drift"


def _pr_observations(args: argparse.Namespace, root: Path, manifest: dict[str, Any]):
    if args.pr_observations:
        path = repo_guard.assert_inside_repo(
            args.pr_observations
            if args.pr_observations.is_absolute()
            else root / args.pr_observations
        )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read PR observations: {error}") from error
        return _validate_pr_observations(value, manifest)
    if not _has_remote(root):
        return {item["branch"]: [] for item in manifest["slices"]}
    observations = {}
    helper = Path(__file__).with_name("gh.py")
    for item in manifest["slices"]:
        output = cli_common.run_process(
            [
                sys.executable,
                str(helper),
                "cmd",
                "--format",
                "json",
                "pr",
                "list",
                "--head",
                item["branch"],
                "--state",
                "all",
                "--json",
                "number,state,headRefName,baseRefName",
            ],
            cwd=root,
        )
        try:
            observations[item["branch"]] = json.loads(output)
        except json.JSONDecodeError as error:
            raise ValueError("gh.py returned malformed PR observations") from error
    return _validate_pr_observations(observations, manifest)


def _validate_pr_observations(
    value: Any, manifest: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    expected_branches = {item["branch"] for item in manifest["slices"]}
    if not isinstance(value, dict) or set(value) != expected_branches:
        raise ValueError("PR observations must contain exactly every lifecycle branch")
    expected_keys = {"number", "state", "headRefName", "baseRefName"}
    for branch, prs in value.items():
        if not isinstance(prs, list):
            raise ValueError(f"PR observations for {branch} must be an array")
        for pr in prs:
            if (
                not isinstance(pr, dict)
                or set(pr) != expected_keys
                or not isinstance(pr["number"], int)
                or isinstance(pr["number"], bool)
                or not all(
                    isinstance(pr[key], str)
                    for key in ("state", "headRefName", "baseRefName")
                )
            ):
                raise ValueError(f"PR observations for {branch} are malformed")
    return value


def _pr_status(item: dict[str, Any], observations: dict[str, Any]) -> str:
    prs = observations.get(item["branch"], [])
    if not isinstance(prs, list) or len(prs) > 1:
        return "blocked"
    if not prs:
        return "fresh"
    pr = prs[0]
    if not isinstance(pr, dict):
        return "blocked"
    expected = {"number", "state", "headRefName", "baseRefName"}
    if set(pr) != expected:
        return "blocked"
    if (
        pr["state"] != "OPEN"
        or pr["headRefName"] != item["branch"]
        or pr["baseRefName"] != item["intended_base"]
    ):
        return "blocked"
    return "fresh"


def refresh(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Inspect drift and optionally rebase the affected local suffix."""
    manifest, stack_plan = _stack_plan(root, args.lifecycle_id)
    if (
        args.apply_rebase
        and git("branch", "--show-current", cwd=root) != manifest["source_branch"]
    ):
        raise ValueError("Refresh rebase requires the source branch checked out")
    if args.fetch and _has_remote(root):
        git("fetch", "--prune", cwd=root)
    base = manifest["base_branch"]
    source_head = manifest["source_head"]
    merge_base = git("merge-base", base, source_head, cwd=root)
    base_head = git("rev-parse", base, cwd=root)
    observations = _pr_observations(args, root, manifest)
    statuses = {}
    for item in manifest["slices"]:
        checks = (
            _pr_status(item, observations),
            _local_status(root, item),
            _sync_status(root, item["branch"]),
        )
        statuses[item["branch"]] = next(
            (status for status in checks if status != "fresh"), "fresh"
        )
    blocking = ("blocked", "diverged", "remote-ahead", "missing-remote", "local-drift")
    if _dirty(root):
        classification = "blocked"
    else:
        classification = next(
            (
                status
                for status in (*blocking, "local-ahead")
                if status in statuses.values()
            ),
            "stale-base" if base_head != merge_base else "fresh",
        )
    first = next(
        (
            index
            for index, item in enumerate(manifest["slices"])
            if classification == "stale-base" or statuses[item["branch"]] != "fresh"
        ),
        len(manifest["slices"]),
    )
    affected = [item["branch"] for item in manifest["slices"][first:]]
    result = {
        "operation": "refresh",
        "lifecycle_id": args.lifecycle_id,
        "classification": classification,
        "branches": statuses,
        "affected": affected,
        "fetched": bool(args.fetch and _has_remote(root)),
    }
    if not args.apply_rebase or not affected:
        return result
    _clean(root)
    if classification != "stale-base":
        raise ValueError(
            f"Cannot rebase lifecycle classified as {classification}; "
            "only clean stale-base is allowed"
        )
    paths = [Path(item["worktree"]) for item in stack_plan["items"]] + [root]
    if any(not path.is_dir() for path in paths):
        missing = next(path for path in paths if not path.is_dir())
        raise ValueError(f"Missing stack worktree: {missing}")
    for path in paths:
        _clean(path)
    all_items = stack_plan["items"] + [
        {"branch": manifest["source_branch"], "start": manifest["source_head"]}
    ]
    original_tips = {
        item["branch"]: git("rev-parse", item["branch"], cwd=root) for item in all_items
    }
    old_parent = merge_base
    new_parent = base
    try:
        for item, path in zip(all_items, paths, strict=True):
            git("rebase", "--onto", new_parent, old_parent, item["branch"], cwd=path)
            old_parent = item["start"]
            new_parent = item["branch"]
    except Exception:
        for item, path in zip(all_items, paths, strict=True):
            try:
                git("rebase", "--abort", cwd=path)
            except cli_common.ExternalCommandError:
                pass
            git("reset", "--hard", original_tips[item["branch"]], cwd=path)
        raise

    try:
        rebuilt = []
        parent = base
        for item in manifest["slices"]:
            commits = git(
                "rev-list", "--reverse", f"{parent}..{item['branch']}", cwd=root
            ).splitlines()
            if not commits:
                raise RuntimeError(f"Rebase produced an empty slice: {item['branch']}")
            rebuilt.append(
                {
                    **item,
                    "commits": commits,
                    "boundary": {
                        "first": commits[0],
                        "last": commits[-1],
                        "count": len(commits),
                    },
                    "tree": git("rev-parse", f"{item['branch']}^{{tree}}", cwd=root),
                }
            )
            parent = item["branch"]
        updated = {
            **manifest,
            "base_head": git("rev-parse", base, cwd=root),
            "source_head": git("rev-parse", "HEAD", cwd=root),
            "source_tree": git("rev-parse", "HEAD^{tree}", cwd=root),
            "slices": rebuilt,
        }
        branch_state.write_lifecycle(root, updated)
    except Exception:
        for item, path in zip(all_items, paths, strict=True):
            git("reset", "--hard", original_tips[item["branch"]], cwd=path)
        raise
    result["status"] = "rebased"
    return result


def parser() -> argparse.ArgumentParser:
    """Build the command parser."""
    result = argparse.ArgumentParser(description=__doc__)
    repo_guard.add_bypass_guard_argument(result)
    commands = result.add_subparsers(dest="command", required=True)
    breakdown_parser = commands.add_parser("breakdown")
    breakdown_parser.add_argument("--base")
    breakdown_parser.add_argument("--lifecycle-id")
    breakdown_parser.add_argument("--issue-id")
    breakdown_parser.add_argument(
        "--slice", dest="slices", action="append", type=_parse_slice
    )
    breakdown_parser.add_argument("--apply", dest="apply_plan", type=Path)
    breakdown_parser.add_argument("--json", action="store_true")
    stack_parser = commands.add_parser("stack")
    stack_parser.add_argument("lifecycle_id")
    stack_parser.add_argument("--apply", action="store_true")
    stack_parser.add_argument("--json", action="store_true")
    refresh_parser = commands.add_parser("refresh")
    refresh_parser.add_argument("lifecycle_id")
    refresh_parser.add_argument("--fetch", action="store_true")
    refresh_parser.add_argument("--apply-rebase", action="store_true")
    refresh_parser.add_argument("--pr-observations", type=Path)
    refresh_parser.add_argument("--json", action="store_true")
    for command in (breakdown_parser, stack_parser, refresh_parser):
        repo_guard.add_bypass_guard_argument(
            command,
            default=argparse.SUPPRESS,
            dest="subcommand_bypass_guard",
        )
    return result


def _human(value: dict[str, Any]) -> str:
    lines = [
        f"{key.upper()}={value[key]}"
        for key in value
        if key not in {"items", "slices", "manifest"}
    ]
    lines.extend(
        f"BRANCH={item['branch']} PATH={item['worktree']}"
        for item in value.get("items", [])
    )
    lines.extend(
        f"SLICE={item['order']} BRANCH={item['branch']} COMMITS={len(item['commits'])}"
        for item in value.get("slices", [])
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse branch arguments and combine global and subcommand bypass roots."""
    args = parser().parse_args(argv)
    args.bypass_guard.extend(getattr(args, "subcommand_bypass_guard", []))
    return args


def main() -> int:
    """Run the selected lifecycle operation."""
    args = parse_args()
    try:
        with repo_guard.bypass_guard(args.bypass_guard):
            root = _root()
            if args.command == "breakdown":
                if not args.apply_plan and (
                    not args.base or not args.lifecycle_id or not args.issue_id
                ):
                    raise ValueError(
                        "Planning requires --base, --lifecycle-id, and --issue-id"
                    )
                value = breakdown(args, root)
            elif args.command == "stack":
                value = stack(args, root)
            else:
                value = refresh(args, root)
    except (ValueError, RuntimeError, cli_common.ExternalCommandError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return cli_common.EXIT_FAILURE
    print(json.dumps(value, indent=2, sort_keys=True) if args.json else _human(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
