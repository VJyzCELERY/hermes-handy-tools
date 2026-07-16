"""Resolve an open issue or PR to one safe, local worktree.

Usage:
    uv run python .agents/scripts/resolve-target-worktree.py <number-or-url>
<EOF_DESC>
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import repo_guard


_CLOSING_REFERENCE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?"
    r"#(?P<number>[1-9][0-9]*)\b",
    re.IGNORECASE,
)
_MISSING_PR = re.compile(
    r"Could not resolve to a PullRequest with the number of [1-9][0-9]*\. "
    r"\(repository\.pullRequest\)"
)


class TargetError(ValueError):
    """A target cannot be safely resolved to one worktree."""


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)


def _git(root: Path, *args: str) -> str:
    result = _run(["git", *args], root)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise TargetError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _target_number(value: str) -> str:
    text = value.strip()
    if text.isdecimal() and int(text) > 0:
        return text
    match = re.fullmatch(
        r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:issues|pull)/(\d+)/?",
        text,
    )
    if match and int(match[1]) > 0:
        return match[1]
    raise TargetError("target must be a positive number or a GitHub issue/PR URL")


def _record(payload: str, kind: str) -> dict:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise TargetError(f"gh.py returned malformed {kind} JSON") from error
    if not isinstance(data, dict):
        raise TargetError(f"gh.py returned malformed {kind} JSON")
    return data


def _records(payload: str, kind: str) -> list[dict]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise TargetError(f"gh.py returned malformed {kind} JSON") from error
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise TargetError(f"gh.py returned malformed {kind} JSON")
    return data


def _repository(url: object, kind: str) -> str:
    if not isinstance(url, str):
        raise TargetError(f"{kind} URL is missing")
    match = re.fullmatch(
        rf"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/{kind}/[1-9][0-9]*/?",
        url,
    )
    if not match:
        raise TargetError(f"{kind} URL is malformed")
    return match[1]


def _pr_target(data: dict, number: int | None = None) -> dict:
    expected_number = data.get("number")
    fields = ("title", "state", "headRefName", "baseRefName", "headRefOid")
    if (
        not isinstance(expected_number, int)
        or isinstance(expected_number, bool)
        or (number is not None and expected_number != number)
        or any(not isinstance(data.get(field), str) or not data[field] for field in fields)
    ):
        raise TargetError("gh.py returned malformed PR JSON")
    if data["state"] != "OPEN":
        raise TargetError("PR is not open")
    _git_branch(data["headRefName"])
    _head(data["headRefOid"])
    return {
        "kind": "pr",
        "repository": _repository(data.get("url"), "pull"),
        "number": expected_number,
        "url": data["url"],
        "title": data["title"],
        "state": data["state"],
        "branch": data["headRefName"],
        "base": data["baseRefName"],
        "head": data["headRefOid"],
    }


def _closes_issue(body: str, issue: dict) -> bool:
    """Return whether a PR body closes the issue in its repository."""
    for match in _CLOSING_REFERENCE.finditer(body):
        repository = match["repository"]
        if (
            int(match["number"]) == issue["number"]
            and (repository is None or repository.lower() == issue["repository"].lower())
        ):
            return True
    return False


def _linked_open_prs(issue: dict, gh: callable) -> list[dict]:
    payload = gh(
        "cmd",
        "--format",
        "json",
        "pr",
        "list",
        "--repo",
        issue["repository"],
        "--state",
        "open",
        "--limit",
        "1000",
        "--json",
        "number,url,title,state,headRefName,baseRefName,headRefOid,body",
    )
    matches = []
    for data in _records(payload, "PR list"):
        body = data.get("body")
        if body is not None and not isinstance(body, str):
            raise TargetError("gh.py returned malformed PR list JSON")
        if body and _closes_issue(body, issue):
            matches.append(_pr_target(data))
    return matches


def classify_target(value: str, gh: callable) -> dict:
    """Classify an explicit target, preferring an open PR over an issue."""
    number = _target_number(value)
    if "/issues/" in value:
        return _classify_issue(value, number, gh)
    pr_args = (
        "cmd",
        "--format",
        "json",
        "pr",
        "view",
        value,
        "--json",
        "number,url,title,state,headRefName,baseRefName,headRefOid",
    )
    try:
        payload = gh(*pr_args)
    except TargetError as error:
        if str(error) != "PR not found" and not _MISSING_PR.search(str(error)):
            raise
        data = None
    else:
        data = _record(payload, "PR")
    if data is not None:
        return _pr_target(data, int(number))
    return _classify_issue(value, number, gh)


def _classify_issue(value: str, number: str, gh: callable) -> dict:
    issue_args = (
        "fetch",
        "issue",
        value,
        "--json",
        "number,url,title,state",
        "--format",
        "json",
    )
    try:
        data = _record(gh(*issue_args), "issue")
    except TargetError as error:
        raise TargetError("target is neither an open PR nor an eligible issue") from error
    if (
        data.get("number") != int(number)
        or not isinstance(data.get("title"), str)
        or not data["title"]
        or data.get("state") != "OPEN"
    ):
        raise TargetError("gh.py returned malformed or closed issue JSON")
    issue = {
        "kind": "issue",
        "repository": _repository(data.get("url"), "issues"),
        "number": data["number"],
        "url": data["url"],
        "title": data["title"],
        "state": data["state"],
    }
    linked_prs = _linked_open_prs(issue, gh)
    if len(linked_prs) > 1:
        raise TargetError("multiple open PRs close this issue; select one explicitly")
    return linked_prs[0] if linked_prs else issue


def _git_branch(branch: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch):
        raise TargetError(f"invalid branch name: {branch!r}")


def _head(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise TargetError("PR head SHA is malformed")


def _worktrees(root: Path) -> list[dict]:
    records: list[dict] = []
    current: dict | None = None
    for line in _git(root, "worktree", "list", "--porcelain").splitlines():
        if not line:
            if current:
                records.append(current)
                current = None
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current:
                records.append(current)
            path = Path(value).resolve()
            try:
                repo_guard.assert_inside_repo(path)
            except ValueError:
                continue
            current = {"path": path, "branch": None}
        elif current is not None and key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
    if current:
        records.append(current)
    return records


def _state_matches(path: Path, target: dict) -> bool:
    directory = path / ".agents" / "local" / "state" / "goals"
    if not directory.is_dir():
        return False
    for state_path in directory.glob("*.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict) or state.get("repository", "").lower() != target[
            "repository"
        ].lower():
            continue
        if target["kind"] == "issue":
            issue = state.get("issue")
            if isinstance(issue, dict) and issue.get("number") == target["number"]:
                return True
        elif (
            isinstance(state.get("target"), dict)
            and state["target"].get("number") == target["number"]
        ) or any(
            isinstance(pr, dict) and pr.get("number") == target["number"]
            for pr in state.get("prs", [])
            if isinstance(state.get("prs"), list)
        ):
            return True
    return False


def _canonical_branch(target: dict) -> str:
    if target["kind"] == "pr":
        return target["branch"]
    slug = re.sub(r"[^a-z0-9]+", "-", target["title"].lower()).strip("-")
    return f"feat/{target['number']}-{slug[:48] or 'issue'}"


def _safe_candidate(root: Path, candidate: dict) -> None:
    path = candidate["path"]
    if _git(path, "status", "--porcelain"):
        raise TargetError(f"matching worktree is dirty: {path}")
    branch = _git(path, "branch", "--show-current")
    if not branch or branch != candidate["branch"]:
        raise TargetError(f"matching worktree is detached or changed branch: {path}")
    _safe_branch(path, branch, "HEAD")


def _safe_branch(root: Path, branch: str, local_ref: str) -> None:
    remote = f"refs/remotes/origin/{branch}"
    exists = _run(["git", "show-ref", "--verify", "--quiet", remote], root)
    if exists.returncode == 1:
        return
    if exists.returncode:
        raise TargetError(f"could not inspect remote branch for {branch}")
    ahead, behind = _git(
        root, "rev-list", "--left-right", "--count", f"{local_ref}...{remote}"
    ).split()
    if int(ahead):
        raise TargetError(f"matching worktree is ahead of origin/{branch}")
    if int(behind):
        raise TargetError(f"matching worktree is behind origin/{branch}")


def resolve_target(root: Path, target: dict) -> dict:
    """Return one safe worktree result without creating a missing worktree."""
    branch = _canonical_branch(target)
    candidates = [
        worktree
        for worktree in _worktrees(root)
        if worktree["branch"] == branch
        or (target["kind"] == "issue" and _state_matches(worktree["path"], target))
    ]
    if len(candidates) > 1:
        raise TargetError("multiple matching worktrees; select one explicitly")
    if not candidates:
        return {"action": "create", "branch": branch}
    _safe_candidate(root, candidates[0])
    if target["kind"] == "pr" and _git(candidates[0]["path"], "rev-parse", "HEAD") != target["head"]:
        raise TargetError("matching worktree does not match the PR head")
    return {"action": "reuse", "branch": branch, "path": str(candidates[0]["path"])}


def _refresh_pr_ref(root: Path, target: dict) -> None:
    if target["kind"] != "pr":
        return
    branch = target["branch"]
    remote = f"refs/remotes/origin/{branch}"
    _git(root, "fetch", "--no-tags", "origin", f"refs/heads/{branch}:{remote}")
    if _git(root, "rev-parse", remote) != target["head"]:
        raise TargetError("PR head changed during resolution")


def _require_clean_primary(root: Path) -> None:
    worktrees = _worktrees(root)
    if not worktrees or worktrees[0]["path"] != root:
        raise TargetError("worktree acquisition must run from the primary checkout")
    if _git(root, "status", "--porcelain"):
        raise TargetError("primary checkout is dirty")
    if _git(root, "branch", "--show-current") not in {"main", "master"}:
        raise TargetError("primary checkout must be on main or master")


def _origin_repository(root: Path) -> str:
    url = _git(root, "remote", "get-url", "origin")
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        url,
    )
    if not match:
        raise TargetError("origin URL is not a GitHub repository")
    return match[1]


def acquire_target(root: Path, target: dict) -> dict:
    """Reuse or safely create the worktree selected for *target*."""
    _require_clean_primary(root)
    if _origin_repository(root).lower() != target["repository"].lower():
        raise TargetError("target belongs to a foreign repository")
    _refresh_pr_ref(root, target)
    result = resolve_target(root, target)
    if result["action"] == "reuse":
        return result
    branch = result["branch"]
    worktree = root / ".worktrees" / branch.replace("/", "-")
    if worktree.exists():
        raise TargetError(f"canonical worktree path already exists: {worktree}")
    exists = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], root)
    command = [
        sys.executable,
        str(root / ".agents" / "scripts" / "create-worktree.py"),
        branch,
        "--base",
        target.get("base", _git(root, "branch", "--show-current")),
        "--path",
        str(worktree),
    ]
    if exists.returncode == 0:
        _safe_branch(root, branch, branch)
        command.append("--attach")
    elif exists.returncode == 1 and target["kind"] == "pr":
        command.extend(["--track", f"origin/{branch}"])
    elif exists.returncode != 1:
        raise TargetError(f"could not inspect local branch {branch}")
    created = _run(command, root)
    if created.returncode:
        raise TargetError(created.stderr.strip() or "could not create target worktree")
    return {"action": "create", "branch": branch, "path": str(worktree.resolve())}


def _gh(root: Path, *args: str) -> str:
    script = root / ".agents" / "scripts" / "gh.py"
    result = _run([sys.executable, str(script), *args], root)
    if result.returncode:
        raise TargetError(result.stderr.strip() or "gh.py target lookup failed")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Resolve a target and emit one machine-readable acquisition result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--read-only", action="store_true")
    repo_guard.add_bypass_guard_argument(parser)
    args = parser.parse_args(argv)
    try:
        with repo_guard.bypass_guard(args.bypass_guard):
            root = repo_guard.repo_root()
            target = classify_target(args.target, lambda *command: _gh(root, *command))
            result = resolve_target(root, target) if args.read_only else acquire_target(root, target)
            if args.read_only and result["action"] != "reuse":
                raise TargetError("read-only resolution requires an existing worktree")
            result["target"] = target
            print(json.dumps(result, sort_keys=True))
            return 0
    except (TargetError, ValueError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
