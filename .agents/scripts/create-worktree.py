"""Create a new git worktree with a branch based on the current branch.

Usage:
    uv run python .agents/scripts/create-worktree.py <branch-name>

Outputs on success (stdout):
    BRANCH=<branch>
    PATH=<absolute-worktree-path>
    BASE=<base-branch>

On failure, prints actionable instructions for the agent (stderr) and exits 1.
The exit message includes [ACTION] tags so the agent knows what to do next.
<EOF_DESC>
"""

import re
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode == 0:
            return r.stdout.strip()
        return ""
    except Exception:
        return ""


def fail(msg: str, action: str = ""):
    print(f"[FAIL] {msg}", file=sys.stderr)
    if action:
        print(f"[ACTION] {action}", file=sys.stderr)
    sys.exit(1)


def get_main_repo_root() -> Path:
    """Return the main repository root, even when called from inside a worktree.

    - git rev-parse --git-common-dir returns the shared .git dir of the main repo.
    - Its parent is the main repo root.
    """
    common_dir = run(["git", "rev-parse", "--git-common-dir"])
    if not common_dir:
        fail("Not inside a git repository.", "Run preflight-start.py first to ensure you are in a valid repo.")
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = Path.cwd() / common_path
    main_root = common_path.resolve().parent
    if not (main_root / ".git").exists() and not (main_root / "AGENTS.md").exists():
        toplevel = run(["git", "rev-parse", "--show-toplevel"])
        if toplevel:
            return Path(toplevel).resolve()
        fail("Could not determine main repository root.", "Ensure you are inside a git worktree or the main repo.")
    return main_root


def main():
    if len(sys.argv) < 2:
        fail(
            "No branch name provided.",
            "Usage: uv run python .agents/scripts/create-worktree.py <branch-name>\n"
            "Example: uv run python .agents/scripts/create-worktree.py feat/new-ui",
        )

    branch = sys.argv[1].strip()
    if not re.match(r'^[\w/.-]+$', branch):
        fail(
            f"Invalid branch name: '{branch}'.",
            "Use alphanumeric characters, dashes, dots, or slashes. "
            "Example: feat/new-ui, fix/login-bug, test/my-feature",
        )

    # Detect main repo root (works from inside worktrees)
    main_repo = get_main_repo_root()

    # Detect current branch (base)
    BASE_BRANCH = run(["git", "branch", "--show-current"])
    if not BASE_BRANCH:
        fail(
            "Detached HEAD detected.",
            "Checkout a branch first: git checkout <branch-name>",
        )

    # Check if branch already exists
    try:
        subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=True, capture_output=True,
        )
        fail(
            f"Branch '{branch}' already exists.",
            f"Choose a different branch name. The branch '{branch}' already exists locally. "
            f"Suggestions: add a suffix like '-v2' or use a more specific name.",
        )
    except subprocess.CalledProcessError:
        pass

    # Sanitize worktree directory name
    sanitized = branch.replace("/", "_")
    worktree_path = main_repo / ".worktrees" / sanitized

    if worktree_path.exists():
        fail(
            f"Worktree path already exists: {worktree_path}",
            f"Run 'git worktree remove {worktree_path}' first, or choose a different branch name.",
        )

    # Create the worktree
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), BASE_BRANCH],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        fail(
            f"Worktree creation failed: {result.stderr.strip()}",
            "Check the error message above. Common issues: invalid branch name, "
            "BASE_BRANCH not found locally.",
        )

    # Verify
    if not worktree_path.exists():
        fail(
            f"Worktree was not created at {worktree_path}",
            "The git command succeeded but the directory is missing. "
            "Run 'git worktree list' to see current worktrees.",
        )

    # Store base branch in git config so agents can discover it later
    subprocess.run(
        ["git", "config", "--local", "worktree.base-branch", BASE_BRANCH],
        capture_output=True, text=True, check=False,
        cwd=str(worktree_path),
    )

    print(f"BRANCH={branch}")
    print(f"PATH={worktree_path.resolve()}")
    print(f"BASE={BASE_BRANCH}")


if __name__ == "__main__":
    main()
