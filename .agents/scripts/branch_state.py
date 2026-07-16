"""Strict, atomic local state for branch lifecycles."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import repo_guard

VERSION = 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_OID = re.compile(r"[0-9a-f]{40}\Z")
_LIFECYCLE_KEYS = {
    "version",
    "id",
    "issue_id",
    "source_branch",
    "base_branch",
    "base_head",
    "source_head",
    "source_tree",
    "slices",
}
_SLICE_KEYS = {
    "order",
    "id",
    "branch",
    "title",
    "purpose",
    "paths",
    "intended_base",
    "rationale",
    "dependencies",
    "changed_lines",
    "validation",
    "review_disposition",
    "skip_reason",
    "commits",
    "boundary",
    "tree",
}
_BRANCH_KEYS = {
    "version",
    "lifecycle_id",
    "branch",
    "source_worktree",
    "worktree",
}


def _exact(value: dict[str, Any], keys: set[str], label: str) -> None:
    extra = set(value) - keys
    missing = keys - set(value)
    if extra or missing:
        raise ValueError(
            f"Invalid {label} keys; unexpected={sorted(extra)}, missing={sorted(missing)}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_lifecycle(value: Any) -> dict[str, Any]:
    """Validate and return a source lifecycle manifest."""
    if not isinstance(value, dict):
        raise ValueError("Lifecycle must be an object")
    _exact(value, _LIFECYCLE_KEYS, "lifecycle")
    if value["version"] != VERSION:
        raise ValueError(f"Unsupported lifecycle version: {value['version']}")
    if not isinstance(value["id"], str) or not _ID.fullmatch(value["id"]):
        raise ValueError("Invalid lifecycle id")
    for key in ("issue_id", "source_branch", "base_branch"):
        _text(value[key], key)
    for key in ("base_head", "source_head", "source_tree"):
        if not isinstance(value[key], str) or not _OID.fullmatch(value[key]):
            raise ValueError(f"{key} must be a full Git object id")
    slices = value["slices"]
    if not isinstance(slices, list) or not slices:
        raise ValueError("slices must be a non-empty array")
    branches: set[str] = set()
    for order, item in enumerate(slices, 1):
        if not isinstance(item, dict):
            raise ValueError("Each slice must be an object")
        _exact(item, _SLICE_KEYS, "slice")
        if item["order"] != order:
            raise ValueError("Slice order must be contiguous and one-based")
        branch = _text(item["branch"], "slice branch")
        if branch in branches:
            raise ValueError(f"Duplicate slice branch: {branch}")
        branches.add(branch)
        for key in ("id", "title", "purpose", "intended_base", "rationale"):
            _text(item[key], key)
        if not isinstance(item["paths"], list) or not all(
            isinstance(path, str) and path for path in item["paths"]
        ):
            raise ValueError("Slice paths must be non-empty strings")
        if not isinstance(item["dependencies"], list):
            raise ValueError("Slice dependencies must be an array")
        if item["review_disposition"] not in {"required", "optional", "skipped"}:
            raise ValueError("Invalid review disposition")
        if item["review_disposition"] == "skipped" and not item["skip_reason"]:
            raise ValueError("Skipped review requires a reason")
        commits = item["commits"]
        if not isinstance(commits, list) or not commits:
            raise ValueError("Slice commits must be a non-empty array")
        if any(not isinstance(oid, str) or not _OID.fullmatch(oid) for oid in commits):
            raise ValueError("Slice commits must be full Git object ids")
        if item["boundary"] != {
            "first": commits[0],
            "last": commits[-1],
            "count": len(commits),
        }:
            raise ValueError("Slice boundary must exactly match commits")
        if not isinstance(item["tree"], str) or not _OID.fullmatch(item["tree"]):
            raise ValueError("Slice tree must be a full Git object id")
        expected_base = (
            value["base_branch"] if order == 1 else slices[order - 2]["branch"]
        )
        expected_dependencies = [] if order == 1 else [slices[order - 2]["id"]]
        if item["intended_base"] != expected_base:
            raise ValueError("Slice intended bases must form the lifecycle chain")
        if item["dependencies"] != expected_dependencies:
            raise ValueError("Slice dependencies must form the lifecycle chain")
    if slices[-1]["branch"] != value["source_branch"]:
        raise ValueError("Source branch must be the final slice")
    return value


def validate_branch_state(value: Any) -> dict[str, Any]:
    """Validate and return worktree-local branch facts."""
    if not isinstance(value, dict):
        raise ValueError("Branch state must be an object")
    _exact(value, _BRANCH_KEYS, "branch state")
    if value["version"] != VERSION:
        raise ValueError(f"Unsupported branch state version: {value['version']}")
    if not isinstance(value["lifecycle_id"], str) or not _ID.fullmatch(
        value["lifecycle_id"]
    ):
        raise ValueError("Invalid lifecycle id")
    _text(value["branch"], "branch")
    for key in ("source_worktree", "worktree"):
        path = Path(_text(value[key], key))
        if not path.is_absolute():
            raise ValueError(f"{key} must be absolute")
        repo_guard.assert_inside_repo(path)
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> Path:
    path = repo_guard.assert_inside_repo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _read(path: Path, validator) -> dict[str, Any]:
    path = repo_guard.assert_inside_repo(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read valid state from {path}: {error}") from error
    return validator(value)


def lifecycle_path(source_worktree: str | Path, lifecycle_id: str) -> Path:
    """Return the guarded source lifecycle path."""
    if not _ID.fullmatch(lifecycle_id):
        raise ValueError("Invalid lifecycle id")
    root = repo_guard.assert_inside_repo(source_worktree)
    return root / ".agents/local/state/lifecycles" / f"{lifecycle_id}.json"


def write_lifecycle(source_worktree: str | Path, value: dict[str, Any]) -> Path:
    """Atomically write a validated source lifecycle."""
    validate_lifecycle(value)
    return _atomic_write(lifecycle_path(source_worktree, value["id"]), value)


def read_lifecycle(source_worktree: str | Path, lifecycle_id: str) -> dict[str, Any]:
    """Read and validate a source lifecycle."""
    return _read(lifecycle_path(source_worktree, lifecycle_id), validate_lifecycle)


def write_branch_state(worktree: str | Path, value: dict[str, Any]) -> Path:
    """Atomically write validated worktree-local facts."""
    validate_branch_state(value)
    root = repo_guard.assert_inside_repo(worktree)
    return _atomic_write(root / ".agents/local/state/branch.json", value)


def read_branch_state(worktree: str | Path) -> dict[str, Any]:
    """Read and validate worktree-local facts."""
    root = repo_guard.assert_inside_repo(worktree)
    return _read(root / ".agents/local/state/branch.json", validate_branch_state)
