"""Session start pre-flight: detect OS + establish project boundary.

Run this at the start of every session. It tells the agent:
  1. Which OS it's running on (so it uses correct commands/paths)
  2. Where the project root is (so it never operates outside it)

If temp files are needed, use ./tmp/ (already gitignored) — NOT
system /tmp/ — and clean up after yourself.

Usage:
    uv run python .agents/scripts/preflight-start.py

Exits 0. Prints OS and project boundary info to stdout.
<EOF_DESC>
"""

import platform, subprocess, sys
from pathlib import Path


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main():
    # ── OS Detection ──
    system = platform.system().lower()
    release = platform.release()
    machine = platform.machine()

    if system == "darwin":
        os_name = "macOS"
    elif system == "windows":
        os_name = "Windows"
    elif system == "linux":
        os_name = "Linux"
    else:
        os_name = system

    print(f"[OS] {os_name} {release} ({machine})")
    print(f"[OS] Python: {sys.version.split()[0]}")

    if os_name == "Windows":
        print("[OS] Note: Use PowerShell-compatible commands. Path separator is '\\'.")
        print("[OS] Note: Use `where` instead of `which` for finding executables.")
    elif os_name == "macOS":
        print("[OS] Note: Uses BSD-style commands. Install GNU utils via Homebrew if needed.")
    elif os_name == "Linux":
        print("[OS] Note: Standard GNU/Linux environment. Use apt/yum/pacman for packages.")

    # ── Project Boundary ──
    root = run(["git", "rev-parse", "--show-toplevel"])
    if root:
        print(f"[BOUNDARY] Project root: {root}")
        print(f"[BOUNDARY] Do NOT operate outside this directory.")
        print(f"[BOUNDARY] Approved temp directory: {root}/tmp/ (auto-cleaned)")
        print(f"[BOUNDARY] Do NOT use system /tmp/ for repo work — use ./tmp/ instead.")
    else:
        print("[BOUNDARY] WARNING: Not inside a git repository — boundary unknown.")
        print("[BOUNDARY] Proceed with caution and stay within the working directory.")

    # ── Git Branch Info ──
    branch = run(["git", "branch", "--show-current"])
    if branch:
        print(f"[GIT] Branch: {branch}")
        base = run(["git", "config", "--local", "worktree.base-branch"])
        if not base:
            base = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"])
            if base and "/" in base:
                base = base.split("/", 1)[1]
        if base:
            print(f"[GIT] Base branch: {base}")
        pr = run(["gh", "pr", "view", "--json", "number", "--jq", ".number"])
        if pr:
            print(f"[GIT] PR: #{pr}")
        else:
            print(f"[GIT] PR: none")

    # Ensure ./tmp/ exists
    if root:
        tmp_dir = Path(root) / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        print(f"[BOUNDARY] ./tmp/ is ready at: {tmp_dir}")


if __name__ == "__main__":
    main()
