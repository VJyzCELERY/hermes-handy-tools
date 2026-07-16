"""Update a review report's commit range to the current local HEAD.

Usage:
    uv run python .agents/scripts/update-commit-range.py <review-path>
<EOF_DESC>
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import repo_guard
from cli_common import EXIT_EXTERNAL, ExternalCommandError, run_process

SHA_PATTERN = r"[0-9a-f]{40}"
RANGE_PATTERN = re.compile(
    rf"^\*\*Commit Range\*\*:[ \t]*({SHA_PATTERN})\.\.\.({SHA_PATTERN})[ \t]*$",
    re.MULTILINE,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Update a review report's commit range to local HEAD."
    )
    parser.add_argument("review_path", help="path to the review Markdown file")
    return parser


def check_branch_health() -> dict:
    """Return current branch synchronization details."""
    branch = run_process(["git", "branch", "--show-current"])
    head = run_process(["git", "rev-parse", "HEAD"])
    if not branch:
        return {
            "status": "detached",
            "ahead": 0,
            "behind": 0,
            "head": head,
            "branch": "",
        }

    upstream = run_process(
        [
            "git",
            "for-each-ref",
            "--format=%(upstream:short)",
            f"refs/heads/{branch}",
        ]
    )
    if not upstream:
        return {
            "status": "no_remote",
            "ahead": 0,
            "behind": 0,
            "head": head,
            "branch": branch,
        }

    counts = run_process(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"]
    ).split()
    if len(counts) != 2 or not all(value.isdigit() for value in counts):
        raise ValueError(f"Git returned malformed ahead/behind counts: {counts}")
    ahead, behind = map(int, counts)
    status = "up_to_date"
    if ahead and behind:
        status = "diverged"
    elif ahead:
        status = "ahead"
    elif behind:
        status = "behind"
    return {
        "status": status,
        "ahead": ahead,
        "behind": behind,
        "head": head,
        "branch": branch,
    }


def write_atomic(path: Path, content: str) -> None:
    """Atomically replace a repository file from its own directory."""
    path = repo_guard.assert_inside_repo(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            file.write(content)
            temporary = repo_guard.assert_inside_repo(file.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _validated_range(content: str) -> re.Match:
    matches = list(RANGE_PATTERN.finditer(content))
    if len(matches) != 1 or content.count("**Commit Range**") != 1:
        raise ValueError("expected exactly one valid **Commit Range**: BASE...HEAD line")
    return matches[0]


def main(argv=None) -> int:
    """Update the requested review report and return an exit status."""
    args = build_parser().parse_args(argv)
    try:
        path = repo_guard.assert_inside_repo(args.review_path)
    except ValueError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"[FAIL] Review path is not a file: {path}", file=sys.stderr)
        return 1

    try:
        content = path.read_text(encoding="utf-8")
        existing = _validated_range(content)
        health = check_branch_health()
        if health["status"] == "detached":
            raise ValueError("Detached HEAD; cannot determine branch health")
        if health["status"] in {"behind", "diverged"}:
            raise ValueError(
                f"Branch is {health['status']} "
                f"({health['ahead']} ahead, {health['behind']} behind)"
            )
        head = health["head"]
        base = existing.group(1)
        if not re.fullmatch(SHA_PATTERN, head) or not re.fullmatch(SHA_PATTERN, base):
            raise ValueError(f"Git returned malformed SHAs: base={base} head={head}")
        new_range = f"{base}...{head}"
        if existing.group(0).split(":", 1)[1].strip() == new_range:
            print(f"[OK] Commit Range already up to date: {new_range}")
            return 0
        updated = (
            content[: existing.start()]
            + f"**Commit Range**: {new_range}"
            + content[existing.end() :]
        )
        write_atomic(path, updated)
    except ExternalCommandError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    except (OSError, UnicodeError, ValueError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    detail = ""
    if health["status"] == "ahead":
        detail = f" (local ahead by {health['ahead']})"
    elif health["status"] == "no_remote":
        detail = " (no tracking branch)"
    print(f"[OK] Commit Range updated to {new_range}{detail} in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
