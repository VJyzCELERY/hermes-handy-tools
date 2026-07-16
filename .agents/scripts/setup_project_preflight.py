"""Verify and print the canonical setup-project wiki installation guide."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import repo_guard


GH_SCRIPT = Path(__file__).with_name("gh.py")
REPOSITORY_ROUTE = "repos/VJyzCELERY/MAIN-PROJECT-TEMPLATE"
REPOSITORY_FULL_NAME = "VJyzCELERY/MAIN-PROJECT-TEMPLATE"
REPOSITORY_URL = "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE"
WIKI_URL = f"{REPOSITORY_URL}/wiki"
WIKI_REPOSITORY = f"{REPOSITORY_FULL_NAME}.wiki"
WIKI_CLONE_NAME = "setup-project-wiki"
AGENTS_FILE_NAME = "Agents.md"
ACCESS_ERROR = (
    "Unable to retrieve the canonical guide. Install and authenticate `gh`; the current "
    "account may not access the private template repository."
)


def _run_gh(output_format: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the repository GitHub wrapper without exposing its output."""
    return subprocess.run(
        [
            sys.executable,
            str(GH_SCRIPT),
            "cmd",
            "--format",
            output_format,
            *args,
        ],
        capture_output=True,
        check=False,
        cwd=repo_guard.repo_root(),
        text=True,
    )


def _clone_directory() -> Path:
    """Return the fixed, guarded wiki clone directory."""
    tmp_dir = repo_guard.repo_root() / "tmp"
    if tmp_dir.is_symlink() or (tmp_dir.exists() and not tmp_dir.is_dir()):
        raise ValueError("repository tmp directory is unsafe")
    tmp_dir.mkdir(exist_ok=True)
    repo_guard.assert_inside_repo(tmp_dir)
    return tmp_dir / WIKI_CLONE_NAME


def _clean_clone_directory(clone_dir: Path) -> None:
    """Remove only the fixed clone directory without following symlinks."""
    if clone_dir.is_symlink():
        clone_dir.unlink()
    elif clone_dir.is_dir():
        shutil.rmtree(clone_dir)
    elif clone_dir.exists():
        clone_dir.unlink()


def main(args: Sequence[str] | None = None) -> int:
    """Print the validated wiki guide and URL, or a safe actionable error."""
    if (sys.argv[1:] if args is None else args):
        print(ACCESS_ERROR, file=sys.stderr)
        return 2

    try:
        result = _run_gh("json", "api", REPOSITORY_ROUTE)
    except OSError:
        print(ACCESS_ERROR, file=sys.stderr)
        return 1

    if result.returncode:
        print(ACCESS_ERROR, file=sys.stderr)
        return 1

    try:
        repository = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(ACCESS_ERROR, file=sys.stderr)
        return 1

    if not isinstance(repository, dict):
        print(ACCESS_ERROR, file=sys.stderr)
        return 1
    if (
        repository.get("full_name") != REPOSITORY_FULL_NAME
        or repository.get("html_url") != REPOSITORY_URL
        or repository.get("has_wiki") is not True
    ):
        print(ACCESS_ERROR, file=sys.stderr)
        return 1

    guide = None
    clone_dir = None
    try:
        clone_dir = _clone_directory()
        _clean_clone_directory(clone_dir)
        clone_dir = repo_guard.assert_inside_repo(clone_dir)
        result = _run_gh(
            "raw",
            "repo",
            "clone",
            WIKI_REPOSITORY,
            str(clone_dir),
            "--",
            "--depth",
            "1",
        )
        if result.returncode == 0:
            agents_guide = clone_dir / AGENTS_FILE_NAME
            if not agents_guide.is_symlink() and agents_guide.is_file():
                guide = repo_guard.assert_inside_repo(agents_guide).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        guide = None
    finally:
        if clone_dir is not None:
            try:
                _clean_clone_directory(clone_dir)
            except (OSError, ValueError):
                guide = None

    if guide is None:
        print(ACCESS_ERROR, file=sys.stderr)
        return 1

    print(guide, end="" if guide.endswith("\n") else "\n")
    print(WIKI_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
