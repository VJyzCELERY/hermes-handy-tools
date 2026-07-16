"""Safely preview and apply version-driven agent-infrastructure updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import repo_guard


MARKER = Path(".agents/template-version.json")
CLONE_NAME = "setup-project-template"
PREVIEW_NAME = ".setup-project-preview.json"
ALIASES = (".opencode", ".codex", ".claude", ".hermes")


class UpdateError(RuntimeError):
    """The update cannot proceed without risking project changes."""


@dataclass(frozen=True)
class Release:
    """A validated template release identity."""

    version: int
    tag: str


@dataclass(frozen=True)
class Action:
    """One exact managed-file operation in a prepared update."""

    path: str
    kind: str
    incoming_hash: str | None
    local_hash: str | None


@dataclass(frozen=True)
class Preview:
    """The immutable result of comparing installed and incoming infrastructure."""

    status: str
    incoming: Release
    actions: tuple[Action, ...]
    conflicts: tuple[str, ...]
    clone_dir: Path


def _clone_dir() -> Path:
    """Return the one repository-local directory used for incoming content."""
    root = repo_guard.repo_root().resolve()
    tmp_dir = root / "tmp"
    if tmp_dir.is_symlink():
        raise UpdateError("Repository tmp directory is a symlink")
    try:
        return repo_guard.assert_inside_repo(repo_guard.tmp_path(CLONE_NAME))
    except ValueError as error:
        raise UpdateError("Temporary clone path escapes the repository") from error


def _remove_clone() -> None:
    """Remove only the fixed temporary clone directory."""
    clone_dir = _clone_dir()
    if clone_dir.is_symlink():
        raise UpdateError(f"Temporary clone path is a symlink: {clone_dir}")
    if clone_dir.exists():
        shutil.rmtree(clone_dir)


def _run_git(args: list[str], cwd: Path) -> bytes:
    """Run Git in a repository-bound directory and return its bytes output."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_guard.assert_inside_repo(cwd),
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise UpdateError(f"Could not run Git: {error}") from error
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise UpdateError(f"Git {' '.join(args)} failed: {detail or result.returncode}")
    return result.stdout


def _validate_relative(path: str) -> str:
    """Return a safe managed path or reject traversal and special names."""
    relative = PurePosixPath(path)
    if (
        not path
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\x00" in path
    ):
        raise UpdateError(f"Unsafe managed path: {path!r}")
    return relative.as_posix()


def _hash(content: bytes | None) -> str | None:
    """Return a stable identity for optional file content."""
    return hashlib.sha256(content).hexdigest() if content is not None else None


def _read_release(content: bytes, description: str) -> Release:
    """Validate a release marker's positive integer version and matching tag."""
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError) as error:
        raise UpdateError(f"Invalid {description} version marker") from error
    if not isinstance(value, dict):
        raise UpdateError(f"Invalid {description} version marker")
    version = value.get("version")
    tag = value.get("tag")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise UpdateError(f"Invalid {description} version marker")
    if tag != f"template-v{version}":
        raise UpdateError(f"Invalid {description} version marker")
    return Release(version, tag)


def _installed_release(root: Path) -> Release | None:
    """Return a valid installed release, treating absent or invalid as legacy."""
    marker = root / MARKER
    if not marker.exists():
        return None
    if marker.is_symlink() or not marker.is_file():
        return None
    try:
        return _read_release(marker.read_bytes(), "installed")
    except UpdateError:
        return None


def _files_from_tree(agents: Path, description: str) -> dict[str, bytes]:
    """Read safe regular managed files, excluding local state and the marker."""
    if not agents.exists():
        return {}
    if agents.is_symlink() or not agents.is_dir():
        raise UpdateError(f"{description} managed directory is not a directory")
    files: dict[str, bytes] = {}
    for path in sorted(agents.rglob("*")):
        relative = path.relative_to(agents)
        if relative.parts[0] == "local" or relative == Path("template-version.json"):
            continue
        if path.is_symlink():
            raise UpdateError(f"{description} managed content contains a symlink: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise UpdateError(f"{description} managed content is not a regular file: {relative}")
        files[_validate_relative(relative.as_posix())] = path.read_bytes()
    return files


def _baseline_files(clone_dir: Path, release: Release) -> dict[str, bytes]:
    """Fetch and validate the installed release tag as the three-way baseline."""
    _run_git(
        ["fetch", "--depth=1", "origin", f"refs/tags/{release.tag}:refs/tags/{release.tag}"],
        clone_dir,
    )
    marker = _run_git(["show", f"{release.tag}:{MARKER.as_posix()}"], clone_dir)
    if _read_release(marker, "installed tag") != release:
        raise UpdateError(f"Installed tag {release.tag} does not match its version marker")

    output = _run_git(["ls-tree", "-r", "-z", release.tag, "--", ".agents"], clone_dir)
    files: dict[str, bytes] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode = metadata.split(maxsplit=1)[0]
        path = raw_path.decode("utf-8", errors="strict")
        if not path.startswith(".agents/"):
            raise UpdateError(f"Unsafe managed path in installed tag: {path!r}")
        relative = _validate_relative(path.removeprefix(".agents/"))
        if relative == "template-version.json" or relative.startswith("local/"):
            continue
        if mode != b"100644" and mode != b"100755":
            raise UpdateError(f"Installed tag managed content is not a regular file: {relative}")
        files[relative] = _run_git(["show", f"{release.tag}:{path}"], clone_dir)
    return files


def _classify(
    baseline: dict[str, bytes], local: dict[str, bytes], incoming: dict[str, bytes]
) -> tuple[tuple[Action, ...], tuple[str, ...]]:
    """Classify safe three-way changes without similarity heuristics."""
    actions: list[Action] = []
    conflicts: list[str] = []
    for path in sorted(set(baseline) | set(local) | set(incoming)):
        base, project, updated = baseline.get(path), local.get(path), incoming.get(path)
        if project == base:
            if updated == base:
                continue
            kind = "add" if base is None else ("remove" if updated is None else "replace")
        elif updated == base or updated == project:
            continue
        elif base is None and project is None:
            kind = "add"
        elif base is None and updated is None:
            continue
        elif updated is None:
            continue
        else:
            kind = "conflict"
            conflicts.append(path)
        actions.append(Action(path, kind, _hash(updated), _hash(project)))
    return tuple(actions), tuple(conflicts)


def _legacy_actions(local: dict[str, bytes], incoming: dict[str, bytes]) -> tuple[Action, ...]:
    """Return the conservative markerless migration additions only."""
    return tuple(
        Action(path, "add", _hash(content), None)
        for path, content in sorted(incoming.items())
        if path not in local
    )


def _clone_source(source: str) -> Path:
    """Clone an incoming template only into the fixed repository-local directory."""
    if not source:
        raise UpdateError("Template source is required")
    root = repo_guard.repo_root()
    clone_dir = _clone_dir()
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    _remove_clone()
    try:
        _run_git(["clone", "--depth=1", "--no-tags", source, str(clone_dir)], root)
    except UpdateError:
        _remove_clone()
        raise
    return clone_dir


def prepare_update(source: str) -> Preview:
    """Prepare an exact current, legacy, or upgrade preview from a template source."""
    root = repo_guard.repo_root()
    clone_dir = _clone_source(source)
    try:
        incoming_marker = clone_dir / MARKER
        if incoming_marker.is_symlink() or not incoming_marker.is_file():
            raise UpdateError("Incoming template has no valid version marker")
        incoming_release = _read_release(incoming_marker.read_bytes(), "incoming")
        installed_release = _installed_release(root)
        if installed_release and incoming_release.version < installed_release.version:
            raise UpdateError("Incoming template version is a downgrade")
        if installed_release and incoming_release.version == installed_release.version:
            _remove_clone()
            return Preview("current", incoming_release, (), (), clone_dir)

        incoming = _files_from_tree(clone_dir / ".agents", "incoming")
        local = _files_from_tree(root / ".agents", "local")
        if installed_release is None:
            return Preview("legacy", incoming_release, _legacy_actions(local, incoming), (), clone_dir)
        baseline = _baseline_files(clone_dir, installed_release)
        actions, conflicts = _classify(baseline, local, incoming)
        return Preview("upgrade", incoming_release, actions, conflicts, clone_dir)
    except Exception:
        _remove_clone()
        raise


def _target_path(root: Path, path: str) -> Path:
    """Return a writable regular-file destination after rejecting symlink escapes."""
    destination = root / ".agents" / _validate_relative(path)
    agents = root / ".agents"
    if agents.exists() and (agents.is_symlink() or not agents.is_dir()):
        raise UpdateError("Local managed directory is not a directory")
    current = agents
    for part in PurePosixPath(path).parts[:-1]:
        current /= part
        if current.exists() and (current.is_symlink() or not current.is_dir()):
            raise UpdateError(f"Unsafe local managed path: {path}")
        current.mkdir(exist_ok=True)
    if destination.is_symlink():
        raise UpdateError(f"Local managed path is a symlink: {path}")
    return destination


def _validate_preview(preview: Preview) -> None:
    """Reject a stale or tampered retained CLI preview before any mutation."""
    root = repo_guard.repo_root()
    marker = preview.clone_dir / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise UpdateError("Prepared incoming version marker is unavailable")
    if _read_release(marker.read_bytes(), "prepared incoming") != preview.incoming:
        raise UpdateError("Prepared preview is stale for its version marker")
    incoming = _files_from_tree(preview.clone_dir / ".agents", "prepared incoming")
    local = _files_from_tree(root / ".agents", "local")
    installed = _installed_release(root)
    if preview.status == "legacy":
        expected_actions, expected_conflicts = _legacy_actions(local, incoming), ()
        if installed is not None:
            raise UpdateError("Prepared legacy preview is stale")
    else:
        if installed is None:
            raise UpdateError("Prepared upgrade preview is stale")
        expected_actions, expected_conflicts = _classify(
            _baseline_files(preview.clone_dir, installed), local, incoming
        )
    if (preview.actions, preview.conflicts) != (expected_actions, expected_conflicts):
        raise UpdateError("Prepared preview is stale or tampered")


def _ensure_aliases(root: Path) -> None:
    """Create absent harness aliases without touching project-owned aliases."""
    for name in ALIASES:
        alias = root / name
        if not alias.exists() and not alias.is_symlink():
            alias.symlink_to(".agents")


def run_preflight() -> None:
    """Run the installed project preflight after a successful update."""
    root = repo_guard.repo_root()
    script = root / ".agents" / "scripts" / "preflight-start.py"
    if not script.is_file() or script.is_symlink():
        raise UpdateError("Updated infrastructure has no safe preflight script")
    result = subprocess.run(
        [sys.executable, str(script)], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise UpdateError(f"Preflight failed: {result.stderr.strip() or result.stdout.strip()}")


def apply_update(preview: Preview, *, confirmed: bool) -> None:
    """Apply a prepared non-conflicting preview and write its marker last."""
    if not confirmed:
        raise UpdateError("Explicit confirmation is required before apply")
    if preview.status == "current":
        return
    if preview.conflicts:
        _remove_clone()
        raise UpdateError("Update has conflicts and requires manual resolution")
    root = repo_guard.repo_root()
    if preview.clone_dir != _clone_dir() or not preview.clone_dir.is_dir():
        raise UpdateError("Prepared preview is unavailable")
    try:
        _validate_preview(preview)
        source = _files_from_tree(preview.clone_dir / ".agents", "prepared incoming")
        for action in preview.actions:
            destination = _target_path(root, action.path)
            current = destination.read_bytes() if destination.exists() else None
            if _hash(current) != action.local_hash:
                raise UpdateError(f"Prepared preview is stale for {action.path}")
            if action.kind == "remove":
                if destination.exists():
                    destination.unlink()
                continue
            content = source.get(action.path)
            if content is None or _hash(content) != action.incoming_hash:
                raise UpdateError(f"Prepared preview is stale for incoming {action.path}")
            destination.write_bytes(content)
        _ensure_aliases(root)
        run_preflight()
        marker = root / MARKER
        if marker.is_symlink():
            raise UpdateError("Local version marker is a symlink")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes((preview.clone_dir / MARKER).read_bytes())
    finally:
        _remove_clone()


def _save_preview(preview: Preview) -> None:
    """Persist the exact preview alongside its retained clone for CLI apply."""
    payload = {
        "status": preview.status,
        "incoming": asdict(preview.incoming),
        "actions": [asdict(action) for action in preview.actions],
        "conflicts": list(preview.conflicts),
    }
    (preview.clone_dir / PREVIEW_NAME).write_text(json.dumps(payload), encoding="utf-8")


def _load_preview() -> Preview:
    """Load a CLI preview only from the fixed prepared clone directory."""
    clone_dir = _clone_dir()
    try:
        payload = json.loads((clone_dir / PREVIEW_NAME).read_text(encoding="utf-8"))
        incoming = Release(**payload["incoming"])
        actions = tuple(Action(**action) for action in payload["actions"])
        conflicts = tuple(payload["conflicts"])
        status = payload["status"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as error:
        raise UpdateError("Prepared preview is unavailable or invalid") from error
    if status not in {"legacy", "upgrade"}:
        raise UpdateError("Prepared preview is unavailable or invalid")
    return Preview(status, incoming, actions, conflicts, clone_dir)


def _require_root(target: str) -> None:
    """Reject setup targets other than the current repository root."""
    if target != "." or Path.cwd().resolve() != repo_guard.repo_root().resolve():
        raise UpdateError("Target must be the current repository root (.)")


def _print_preview(preview: Preview) -> None:
    """Print an exact human-readable preview for command orchestration."""
    print(f"STATUS={preview.status}")
    print(f"INCOMING_VERSION={preview.incoming.version}")
    for action in preview.actions:
        print(f"{action.kind.upper()} {action.path}")
    for path in preview.conflicts:
        print(f"CONFLICT {path}")


def main(argv: list[str] | None = None) -> int:
    """Run the confirmation-gated preview or apply command."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preview_parser = commands.add_parser("preview")
    preview_parser.add_argument("target")
    preview_parser.add_argument("source")
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("target")
    apply_parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        _require_root(args.target)
        if args.command == "preview":
            preview = prepare_update(args.source)
            if preview.status != "current":
                _save_preview(preview)
            _print_preview(preview)
        else:
            apply_update(_load_preview(), confirmed=args.confirm)
            print("STATUS=applied")
    except UpdateError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
