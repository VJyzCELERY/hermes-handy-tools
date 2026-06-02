"""Repo-boundary and temp-path enforcement helpers for agent scripts.

Provides shared path-guard functions so scripts never read, write,
delete, or create paths outside the project root.

Usage:
    from . import repo_guard
    repo_guard.assert_inside_repo(some_path)
    tmp = repo_guard.tmp_path("my-file")
"""

from pathlib import Path
from typing import Union


def _discover_root() -> Path:
    """Walk up from this file's location to find the repo root (has .git or AGENTS.md)."""
    here = Path(__file__).resolve().parent  # .agents/scripts/
    for candidate in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return here.parent.parent  # fallback: two levels up from scripts/


_ROOT = None


def repo_root() -> Path:
    """Return the resolved project root directory."""
    global _ROOT
    if _ROOT is None:
        _ROOT = _discover_root()
    return _ROOT


def assert_inside_repo(path: Union[str, Path]) -> Path:
    """Resolve *path* and return it if it stays inside the project root.

    Raises ValueError if the path escapes the repository root.
    """
    p = Path(path).resolve()
    root = repo_root().resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{p}' escapes the repository root '{root}'. "
            "All file operations must stay inside the project."
        )
    return p


def tmp_path(name: str) -> Path:
    """Return a path under ./tmp/ for *name*, creating parent dirs.

    Raises ValueError if the resolved path escapes ./tmp/ via "..".
    """
    root = repo_root()
    tmp_dir = root / "tmp"
    candidate = (tmp_dir / name).resolve()
    if not str(candidate).startswith(str(tmp_dir.resolve())):
        raise ValueError(
            f"Temp path '{name}' escapes the ./tmp/ directory '{tmp_dir}'. "
            "Use only simple filenames or safe subdirectory names."
        )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate
