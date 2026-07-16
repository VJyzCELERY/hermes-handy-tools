"""Create a Git worktree and record its base branch locally."""

import argparse
import subprocess
import sys
from pathlib import Path

import repo_guard


def fail(message: str, detail: str = "") -> None:
    """Print an actionable failure and exit nonzero."""
    print(f"[FAIL] {message}", file=sys.stderr)
    if detail:
        print(detail, file=sys.stderr)
    raise SystemExit(1)


def git(
    *args: str, cwd: Path | None = None, allowed: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[str]:
    """Run Git and fail with its diagnostic on unexpected results."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        fail(f"Could not run git: {error}")
    if result.returncode not in allowed:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"Git command failed: git {' '.join(args)}", detail)
    return result


def parse_args() -> argparse.Namespace:
    """Parse current and migration-compatible command-line forms."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", help="new branch name")
    parser.add_argument("legacy_base", nargs="?", help="base branch (legacy form)")
    parser.add_argument("--base", help="base branch; defaults to the current branch")
    parser.add_argument("--path", type=Path, help="worktree path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--attach", action="store_true", help="attach an existing local branch"
    )
    mode.add_argument(
        "--track", help="create the branch by tracking an existing remote branch"
    )
    parser.add_argument(
        "--lifecycle-root", type=Path, help="source worktree for nested lifecycle work"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report without changing Git or files"
    )
    repo_guard.add_bypass_guard_argument(parser)
    args = parser.parse_args()
    if args.base and args.legacy_base:
        parser.error("base branch may be provided either positionally or with --base")
    return args


def _create(args: argparse.Namespace) -> None:
    """Create the requested worktree."""
    branch = args.branch.strip()
    validation = git("check-ref-format", "--branch", branch, allowed=(0, 1, 128))
    if validation.returncode:
        fail(f"Invalid branch name: '{branch}'.", validation.stderr.strip())

    common_dir = Path(git("rev-parse", "--git-common-dir").stdout.strip())
    if not common_dir.is_absolute():
        common_dir = Path.cwd() / common_dir
    try:
        main_repo = repo_guard.assert_inside_repo(common_dir.resolve().parent)
    except ValueError as error:
        fail(str(error))

    base = args.base or args.legacy_base
    if not base:
        base = git("branch", "--show-current").stdout.strip()
        if not base:
            fail("Detached HEAD detected.", "Provide a base branch with --base.")

    existing = git(
        "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", allowed=(0, 1)
    )
    if args.attach and existing.returncode:
        fail(f"Branch '{branch}' does not exist for --attach.")
    if not args.attach and not args.track and existing.returncode == 0:
        fail(f"Branch '{branch}' already exists.")
    if args.track:
        tracking = args.track.removeprefix("refs/remotes/")
        remote, separator, remote_branch = tracking.partition("/")
        if not separator or not remote_branch or remote_branch != branch:
            fail("--track must name the requested branch as REMOTE/BRANCH.")
        remote_ref = f"refs/remotes/{tracking}"
        if git("show-ref", "--verify", "--quiet", remote_ref, allowed=(0, 1)).returncode:
            fail(f"Remote branch '{tracking}' does not exist.")
        if existing.returncode == 0:
            fail(f"Branch '{branch}' already exists; use --attach instead.")

    try:
        requested_lifecycle_root = (
            args.lifecycle_root.resolve() if args.lifecycle_root else main_repo
        )
        worktrees_dir = requested_lifecycle_root / ".worktrees"
        lifecycle_root = repo_guard.assert_inside_repo(
            requested_lifecycle_root
        )
        if args.lifecycle_root:
            registered = {
                Path(field.removeprefix("worktree ")).resolve()
                for field in git(
                    "worktree", "list", "--porcelain", "-z", cwd=main_repo
                ).stdout.split("\0")
                if field.startswith("worktree ")
            }
            if lifecycle_root.resolve() not in registered:
                fail("Lifecycle root must be an exact registered Git worktree path.")
        worktrees_dir = repo_guard.assert_inside_repo(worktrees_dir)
        worktree_path = repo_guard.assert_inside_repo(
            args.path if args.path else worktrees_dir / branch.replace("/", "-")
        )
        try:
            relative_path = worktree_path.relative_to(worktrees_dir)
        except ValueError:
            if not args.bypass_guard or worktree_path.is_relative_to(
                repo_guard.repo_root()
            ):
                raise
            relative_path = None
    except ValueError as error:
        fail(f"Worktree path must be inside {worktrees_dir}", str(error))
    if relative_path is not None and not relative_path.parts:
        fail(f"Worktree path must be inside {worktrees_dir}")
    if worktree_path.exists():
        fail(f"Worktree path already exists: {worktree_path}")

    if args.dry_run:
        print(f"BRANCH={branch}")
        print(f"PATH={worktree_path}")
        print(f"BASE={base}")
        print("DRY_RUN=true")
        return

    extension = git(
        "config", "--get", "extensions.worktreeConfig", cwd=main_repo, allowed=(0, 1)
    ).stdout.strip()
    if extension.lower() != "true":
        git("config", "extensions.worktreeConfig", "true", cwd=main_repo)

    try:
        if args.attach:
            git("worktree", "add", str(worktree_path), branch, cwd=main_repo)
        elif args.track:
            git(
                "worktree",
                "add",
                "--track",
                "-b",
                branch,
                str(worktree_path),
                args.track,
                cwd=main_repo,
            )
        else:
            git(
                "worktree", "add", "-b", branch, str(worktree_path), base, cwd=main_repo
            )
    except SystemExit:
        if extension:
            git("config", "extensions.worktreeConfig", extension, cwd=main_repo)
        else:
            git(
                "config",
                "--unset-all",
                "extensions.worktreeConfig",
                cwd=main_repo,
                allowed=(0, 5),
            )
        raise
    if not worktree_path.is_dir():
        fail(f"Worktree was not created at {worktree_path}")
    try:
        git(
            "config",
            "--worktree",
            "worktree.base-branch",
            base,
            cwd=worktree_path,
        )
    except SystemExit:
        try:
            git("worktree", "remove", "--force", str(worktree_path), cwd=main_repo)
        finally:
            if not args.attach:
                git("branch", "-D", branch, cwd=main_repo)
        raise

    print(f"BRANCH={branch}")
    print(f"PATH={worktree_path}")
    print(f"BASE={base}")


def main() -> None:
    """Parse arguments and create the requested worktree."""
    args = parse_args()
    try:
        with repo_guard.bypass_guard(args.bypass_guard):
            _create(args)
    except ValueError as error:
        fail(str(error))


if __name__ == "__main__":
    main()
