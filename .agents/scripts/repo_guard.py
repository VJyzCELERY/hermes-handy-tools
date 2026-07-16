"""Repo-boundary and scoped external-path enforcement helpers for agent scripts.

Usage:
    from . import repo_guard
    repo_guard.assert_inside_repo(some_path)
    tmp = repo_guard.tmp_path("my-file")
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
import argparse
from pathlib import Path
from typing import Union


def _discover_root() -> Path:
    """Return the verified root containing this ``.agents/scripts`` directory."""
    candidate = Path(__file__).resolve().parents[2]
    if not (candidate / ".git").exists() or not (candidate / "AGENTS.md").is_file():
        raise RuntimeError(f"Could not verify repository root at '{candidate}'.")
    return candidate


_ROOT = None
_BYPASS_ROOTS: ContextVar[tuple[Path, ...]] = ContextVar("bypass_roots", default=())


class _AppendBypassRoot(argparse.Action):
    """Append a bypass root without replacing a parent parser's values."""

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        roots = list(getattr(namespace, self.dest, []))
        roots.append(values)
        setattr(namespace, self.dest, roots)


def repo_root() -> Path:
    """Return the resolved project root directory."""
    global _ROOT
    if _ROOT is None:
        _ROOT = _discover_root()
    return _ROOT


def add_bypass_guard_argument(parser, *, default=None, dest="bypass_guard") -> None:
    """Add the shared external-root option to a command parser."""
    parser.add_argument(
        "--bypass-guard",
        action=_AppendBypassRoot,
        type=Path,
        default=[] if default is None else default,
        dest=dest,
        metavar="PATH",
        help="allow guarded operations beneath this absolute external directory",
    )


@contextmanager
def bypass_guard(roots: Sequence[Path]) -> Iterator[None]:
    """Temporarily allow guarded paths beneath explicit external roots."""
    resolved_roots = []
    for root in roots:
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("each --bypass-guard root must be an absolute directory")
        resolved_roots.append(root.resolve())
    token = _BYPASS_ROOTS.set(tuple(resolved_roots))
    try:
        yield
    finally:
        _BYPASS_ROOTS.reset(token)


def assert_inside_repo(path: Union[str, Path]) -> Path:
    """Resolve *path* and return it if it stays inside an allowed root.

    Raises ValueError if the path escapes the repository and bypass roots.
    """
    p = Path(path).resolve()
    root = repo_root().resolve()
    for allowed_root in (root, *_BYPASS_ROOTS.get()):
        try:
            p.relative_to(allowed_root)
        except ValueError:
            continue
        return p
    raise ValueError(
        f"Path '{p}' escapes the repository root '{root}'. "
        "Use --bypass-guard with an explicit external root."
    )


def tmp_path(name: str) -> Path:
    """Return a resolved path under ``./tmp/`` for *name*.

    Raises ValueError if the resolved path escapes ``./tmp/``.
    """
    tmp_dir = (repo_root() / "tmp").resolve()
    candidate = (tmp_dir / name).resolve()
    try:
        candidate.relative_to(tmp_dir)
    except ValueError:
        raise ValueError(
            f"Temp path '{name}' escapes the ./tmp/ directory '{tmp_dir}'. "
            "Use only simple filenames or safe subdirectory names."
        ) from None
    return candidate
