"""Report session OS, repository boundary, and Git context without mutation.

Usage:
    uv run python .agents/scripts/preflight-start.py [--format human|json]

Exits 0 on success, 1 for a local validation failure, or 3 when a required
local process fails. GitHub lookup failures are reported as unavailable.
<EOF_DESC>
"""

import argparse
import json
import platform
import sys
from pathlib import Path

import repo_guard
from cli_common import EXIT_EXTERNAL, ExternalCommandError, run_process


def _os_info() -> dict[str, str]:
    """Return current operating-system details."""
    system = platform.system().lower()
    names = {"darwin": "macOS", "windows": "Windows", "linux": "Linux"}
    return {
        "name": names.get(system, system),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
    }


def _print_human_header(os_info: dict[str, str], root: str) -> None:
    """Print OS and verified repository-boundary information."""
    print(f"[OS] {os_info['name']} {os_info['release']} ({os_info['machine']})")
    print(f"[OS] Python: {os_info['python']}")
    if os_info["name"] == "Windows":
        print("[OS] Note: Use PowerShell-compatible commands. Path separator is '\\'.")
        print("[OS] Note: Use `where` instead of `which` for finding executables.")
    elif os_info["name"] == "macOS":
        print(
            "[OS] Note: Uses BSD-style commands. Install GNU utils via Homebrew "
            "if needed."
        )
    elif os_info["name"] == "Linux":
        print(
            "[OS] Note: Standard GNU/Linux environment. Use apt/yum/pacman "
            "for packages."
        )

    print(f"[BOUNDARY] Project root: {root}")
    print(f"[BOUNDARY] Approved temp directory: {root}/tmp/ (create when needed)")
    print("[BOUNDARY] Do NOT use system /tmp/ for repo work; use ./tmp/ instead.")


def _optional_config(key: str, root: Path) -> str:
    """Read an optional local Git setting without hiding real failures."""
    try:
        return run_process(["git", "config", "--local", "--get", key], cwd=root)
    except ExternalCommandError as error:
        if error.returncode == 1:
            return ""
        raise


def _git_info(root: Path) -> dict[str, str | int | None]:
    """Return local branch and base-branch details."""
    branch = run_process(["git", "branch", "--show-current"], cwd=root)
    info: dict[str, str | int | None] = {
        "branch": branch or None,
        "base_branch": None,
        "pr": None,
    }
    if not branch:
        return info

    base = _optional_config("worktree.base-branch", root)
    if not base:
        merge_ref = _optional_config(f"branch.{branch}.merge", root)
        base = merge_ref.removeprefix("refs/heads/")
    info["base_branch"] = base or None

    return info


def _pr_number(root: Path, branch: str) -> int | None:
    """Return the current branch's open PR number through gh.py."""
    gh_script = repo_guard.assert_inside_repo(
        repo_guard.repo_root() / ".agents" / "scripts" / "gh.py"
    )
    output = run_process(
        [
            sys.executable,
            str(gh_script),
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
        ],
        cwd=root,
    )
    try:
        prs = json.loads(output)
    except json.JSONDecodeError as error:
        raise ExternalCommandError(
            [sys.executable, str(gh_script)],
            f"gh.py returned invalid JSON: {error}",
            stdout=output,
        ) from error
    if not isinstance(prs, list) or (
        prs
        and (not isinstance(prs[0], dict) or not isinstance(prs[0].get("number"), int))
    ):
        raise ExternalCommandError(
            [sys.executable, str(gh_script)],
            "gh.py returned invalid JSON: expected PR records",
            stdout=output,
        )
    return prs[0].get("number") if prs else None


def _print_human_git(info: dict[str, str | int | None]) -> None:
    """Print available local Git context."""
    print(f"[GIT] Branch: {info['branch'] or 'detached HEAD'}")
    if info["base_branch"]:
        print(f"[GIT] Base branch: {info['base_branch']}")


def main(argv: list[str] | None = None) -> int:
    """Run the read-only session preflight and return its exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args(argv)
    os_info = _os_info()

    try:
        root = repo_guard.repo_root()
    except (RuntimeError, ValueError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    if args.format == "human":
        _print_human_header(os_info, str(root))

    try:
        git_info = _git_info(root)
    except ExternalCommandError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return EXIT_EXTERNAL

    if args.format == "human":
        _print_human_git(git_info)

    pr_unavailable = False
    if git_info["branch"]:
        try:
            git_info["pr"] = _pr_number(root, str(git_info["branch"]))
        except ExternalCommandError as error:
            pr_unavailable = True
            print(f"[WARN] PR context unavailable: {error}", file=sys.stderr)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "os": os_info,
                    "boundary": {
                        "root": str(root),
                        "temp_directory": str(root / "tmp"),
                    },
                    "git": git_info,
                }
            )
        )
    else:
        print(
            f"[GIT] PR: #{git_info['pr']}"
            if git_info["pr"]
            else ("[GIT] PR: unavailable" if pr_unavailable else "[GIT] PR: none")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
