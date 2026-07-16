"""Review lifecycle status, finalization, and dry-run remote planning CLI."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import review_common
import repo_guard


GH_SCRIPT = Path(__file__).with_name("gh.py")


def _github_url(value: str, kind: str) -> tuple[str, str, str | None]:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    valid_repo = (
        parsed.scheme == "https" and parsed.netloc == "github.com" and len(parts) == 2
    )
    valid_pr = (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and len(parts) == 4
        and parts[2] == "pull"
        and parts[3].isdigit()
    )
    if (kind == "repository" and not valid_repo) or (
        kind == "pull_request" and not valid_pr
    ):
        raise ValueError(f"invalid GitHub {kind} URL: {value}")
    return parts[0], parts[1], parts[3] if valid_pr else None


def build_remote_plan(
    report_path: Path | str,
    repository: str,
    pull_request: str,
    remote_head: str,
    inspect=None,
) -> dict:
    """Validate linked feedback and return a remote-write plan without executing it."""
    report_path = repo_guard.assert_inside_repo(report_path)
    report = review_common.read_report(report_path)
    feedback = report["remote_feedback"]
    if feedback == "UNLINKED":
        raise ValueError("report has no linked Remote Feedback")
    repository_id = _github_url(repository, "repository")[:2]
    linked_repository_id = _github_url(feedback["repository"], "repository")[:2]
    pr_owner, pr_repo, pr_number = _github_url(pull_request, "pull_request")
    linked_owner, linked_repo, linked_number = _github_url(
        feedback["pull_request"], "pull_request"
    )
    if repository_id != linked_repository_id or repository_id != (pr_owner, pr_repo):
        raise ValueError("repository identity does not match linked feedback")
    if (pr_owner, pr_repo, pr_number) != (linked_owner, linked_repo, linked_number):
        raise ValueError("pull request URL does not match linked feedback")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", remote_head)
        or report["head"] != remote_head
        or feedback["head"] != remote_head
    ):
        raise ValueError("report head does not match supplied remote head")

    current = (inspect or _inspect_remote)(pull_request)
    if (
        current.get("repository") != repository
        or current.get("pull_request") != pull_request
    ):
        raise ValueError(
            "authoritative repository or pull request identity does not match"
        )
    if current.get("head") != remote_head:
        raise ValueError("authoritative pull request head does not match")
    current_items = {item.get("url"): item for item in current.get("items", [])}

    actions = []
    for item in feedback["items"]:
        authoritative = current_items.get(item["url"])
        if not authoritative:
            raise ValueError(
                "linked feedback item is absent from authoritative PR state"
            )
        if authoritative.get("active_human"):
            raise ValueError("active human discussion blocks remote cleanup")
        item_owner, item_repo, item_pr = _github_url(
            item["url"].split("#", 1)[0], "pull_request"
        )
        if (item_owner, item_repo, item_pr) != (pr_owner, pr_repo, pr_number):
            raise ValueError("feedback URL does not match pull request")
        fragment = urlsplit(item["url"]).fragment
        if fragment.startswith("discussion_r"):
            command = "resolve"
        elif fragment.startswith("pullrequestreview"):
            if authoritative.get("author") != current.get("actor"):
                raise ValueError("only actor-owned reviews may be minimized")
            command = "minimize"
        else:
            raise ValueError("feedback URL is not a review discussion")
        marker_key = hashlib.sha256(
            f"{remote_head}:{item['url']}".encode()
        ).hexdigest()[:20]
        marker = f"<!-- review-cleanup:{marker_key} -->"
        actions.append(
            {
                "command": command,
                "url": item["url"],
                "reply": item.get("reply", ""),
                "reply_marker": marker,
                "reply_present": marker in "\n".join(authoritative.get("bodies", [])),
            }
        )
    return {
        "repository": repository,
        "pull_request": pull_request,
        "head": remote_head,
        "actions": actions,
        "writes_performed": False,
    }


def _inspect_remote(pull_request: str) -> dict:
    pr_number = _github_url(pull_request, "pull_request")[2]
    result = subprocess.run(
        [sys.executable, str(GH_SCRIPT), "fetch", "review-state", pr_number],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or "authoritative review inspection failed"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "authoritative review inspection returned malformed JSON"
        ) from error


def _run_gh(arguments: list[str]) -> int:
    return subprocess.run([sys.executable, *arguments], check=False).returncode


def _completed_remote_urls(plan: dict) -> list[str]:
    pr_number = _github_url(plan["pull_request"], "pull_request")[2]
    result = subprocess.run(
        [
            sys.executable,
            str(GH_SCRIPT),
            "fetch",
            "comments",
            pr_number,
            "--urls-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "remote verification failed")
    active = {
        json.loads(line)["url"] for line in result.stdout.splitlines() if line.strip()
    }
    return [action["url"] for action in plan["actions"] if action["url"] not in active]


def apply_remote_feedback(
    report_path: Path | str,
    repository: str,
    pull_request: str,
    remote_head: str,
    sync_remote: bool,
    run_gh=_run_gh,
    verify=None,
    inspect=None,
) -> dict:
    """Apply linked cleanup through gh.py, preserving the report on failure."""
    if not sync_remote:
        raise ValueError("remote cleanup requires explicit --sync-remote")
    plan = build_remote_plan(
        report_path, repository, pull_request, remote_head, inspect
    )
    verify = verify or _completed_remote_urls
    completed = set(verify(plan))
    writes = False
    tmp_dir = repo_guard.assert_inside_repo(Path(__file__).resolve().parents[2] / "tmp")
    tmp_dir.mkdir(exist_ok=True)
    for action in plan["actions"]:
        if action["url"] in completed:
            continue
        commands = []
        reply_path = None
        if action["command"] == "resolve":
            if not action["reply"].strip():
                raise ValueError("inline cleanup requires a reply before resolve")
            if not action["reply_present"]:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=tmp_dir, delete=False
                ) as stream:
                    stream.write(
                        f"{action['reply'].rstrip()}\n\n{action['reply_marker']}\n"
                    )
                    reply_path = repo_guard.assert_inside_repo(stream.name)
                commands.append(
                    [
                        str(GH_SCRIPT),
                        "interact",
                        "reply",
                        action["url"],
                        str(reply_path),
                    ]
                )
        commands.append(
            [
                str(GH_SCRIPT),
                "interact",
                action["command"],
                action["url"],
                *(
                    ["--classifier", "OUTDATED"]
                    if action["command"] == "minimize"
                    else []
                ),
            ]
        )
        try:
            for command in commands:
                if run_gh(command):
                    raise RuntimeError(
                        f"partial remote cleanup failed for {action['url']}; report preserved"
                    )
                writes = True
        finally:
            if reply_path:
                reply_path.unlink(missing_ok=True)
    remaining = {
        action["url"]
        for action in plan["actions"]
        if action["url"] not in set(verify(plan))
    }
    if remaining:
        raise RuntimeError(
            f"partial remote cleanup verification failed: {', '.join(sorted(remaining))}"
        )
    return {**plan, "state": "REMOTE_APPLIED", "writes_performed": writes}


def _log_report(path: Path) -> None:
    command = [
        sys.executable,
        str(Path(__file__).with_name("review-log.py")),
        "--log-create",
        str(path),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "review log failed"
        )


def finalize_report(
    report_path: Path | str,
    archive_dir: Path | str = "reviews/archives",
    current_head: str | None = None,
    log_report=_log_report,
    create_fresh=None,
) -> dict:
    """Log and archive a completed report before optionally creating a fresh one."""
    source = repo_guard.assert_inside_repo(report_path)
    if current_head is None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "cannot determine current HEAD")
        current_head = result.stdout.strip()
    status = review_common.classify_report(source, current_head)
    if status["state"] not in {"COMPLETE", "CLEAN"}:
        raise ValueError(f"cannot finalize review in {status['state']} state")
    archive_dir = repo_guard.assert_inside_repo(archive_dir)
    branch = re.sub(r"[^A-Za-z0-9_.-]+", "_", status["branch"])
    destination = repo_guard.assert_inside_repo(
        archive_dir / f"{source.stem}__{branch}__{status['head'][:12]}{source.suffix}"
    )
    if destination.exists():
        raise ValueError(f"archive already exists: {destination}")
    log_report(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, destination)
        if create_fresh:
            create_fresh()
    except Exception:
        if destination.exists() and not source.exists():
            os.replace(destination, source)
        raise
    return {"state": "ARCHIVED", "source": str(source), "archive": str(destination)}


def _emit(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, sort_keys=True))
    else:
        print(
            f"{data.get('state', 'REMOTE_PLAN')}: {data.get('path', data.get('archive', ''))}"
        )


def main(argv=None) -> int:
    """Run the review workflow CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    commands = parser.add_subparsers(dest="action", required=True)
    status = commands.add_parser("status")
    status.add_argument("report")
    status.add_argument("--head")
    finalize = commands.add_parser("finalize")
    finalize.add_argument("report")
    finalize.add_argument("--archive-dir", default="reviews/archives")
    finalize.add_argument("--head")
    remote = commands.add_parser("remote-plan")
    remote.add_argument("report")
    remote.add_argument("--repository", required=True)
    remote.add_argument("--pull-request", required=True)
    remote.add_argument("--remote-head", required=True)
    apply_remote = commands.add_parser("remote-apply")
    apply_remote.add_argument("report")
    apply_remote.add_argument("--repository", required=True)
    apply_remote.add_argument("--pull-request", required=True)
    apply_remote.add_argument("--remote-head", required=True)
    apply_remote.add_argument("--sync-remote", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            result = review_common.classify_report(args.report, args.head)
        elif args.action == "finalize":
            result = finalize_report(args.report, args.archive_dir, args.head)
        elif args.action == "remote-plan":
            result = build_remote_plan(
                args.report, args.repository, args.pull_request, args.remote_head
            )
        else:
            result = apply_remote_feedback(
                args.report,
                args.repository,
                args.pull_request,
                args.remote_head,
                args.sync_remote,
            )
        _emit(result, args.as_json)
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        if args.as_json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
