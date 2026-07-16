"""Tests for local branch lifecycle state."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import branch_state


def lifecycle() -> dict:
    """Return a valid minimal source lifecycle."""
    return {
        "version": 1,
        "id": "issue-42",
        "issue_id": "42",
        "source_branch": "feature/source",
        "base_branch": "main",
        "base_head": "f" * 40,
        "source_head": "a" * 40,
        "source_tree": "b" * 40,
        "slices": [
            {
                "order": 1,
                "id": "slice-1",
                "branch": "feature/one",
                "title": "Core change",
                "purpose": "Introduce the core change.",
                "paths": ["file.txt"],
                "intended_base": "main",
                "rationale": "Independent review surface.",
                "dependencies": [],
                "changed_lines": {"total": 1, "review_budget": 1},
                "validation": {
                    "command": "uv run pytest",
                    "status": "deferred",
                    "reason": "planned",
                },
                "review_disposition": "required",
                "skip_reason": None,
                "commits": ["c" * 40],
                "boundary": {"first": "c" * 40, "last": "c" * 40, "count": 1},
                "tree": "d" * 40,
            },
            {
                "order": 2,
                "id": "slice-2",
                "branch": "feature/source",
                "title": "Integration",
                "purpose": "Complete the source branch.",
                "paths": ["file.txt"],
                "intended_base": "feature/one",
                "rationale": "Final integration slice.",
                "dependencies": ["slice-1"],
                "changed_lines": {"total": 1, "review_budget": 1},
                "validation": {
                    "command": "uv run pytest",
                    "status": "deferred",
                    "reason": "planned",
                },
                "review_disposition": "required",
                "skip_reason": None,
                "commits": ["e" * 40],
                "boundary": {"first": "e" * 40, "last": "e" * 40, "count": 1},
                "tree": "b" * 40,
            },
        ],
    }


def test_lifecycle_round_trip_uses_versioned_source_path(tmp_path):
    path = branch_state.write_lifecycle(tmp_path, lifecycle())

    assert path == tmp_path / ".agents/local/state/lifecycles/issue-42.json"
    assert branch_state.read_lifecycle(tmp_path, "issue-42") == lifecycle()
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(extra=True),
        lambda value: value.update(version=2),
        lambda value: value["slices"][0].update(order=2),
        lambda value: value["slices"][0].update(commits=[]),
        lambda value: value.update(id="../escape"),
    ],
)
def test_lifecycle_rejects_non_schema_data(tmp_path, change):
    value = lifecycle()
    change(value)

    with pytest.raises(ValueError):
        branch_state.write_lifecycle(tmp_path, value)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["slices"][-1].update(branch="feature/not-source"),
        lambda value: value["slices"][0].update(intended_base="wrong"),
        lambda value: value["slices"][1].update(intended_base="main"),
        lambda value: value["slices"][1].update(dependencies=[]),
    ],
)
def test_lifecycle_rejects_broken_source_base_or_dependency_chain(change):
    value = lifecycle()
    change(value)

    with pytest.raises(ValueError):
        branch_state.validate_lifecycle(value)


def test_branch_state_contains_only_local_facts(tmp_path):
    value = {
        "version": 1,
        "lifecycle_id": "issue-42",
        "branch": "feature/one",
        "source_worktree": str(tmp_path),
        "worktree": str(tmp_path / ".worktrees/issue-42/feature_one"),
    }

    path = branch_state.write_branch_state(tmp_path, value)

    assert json.loads(path.read_text(encoding="utf-8")) == value
    assert branch_state.read_branch_state(tmp_path) == value
    with pytest.raises(ValueError, match="unexpected"):
        branch_state.write_branch_state(tmp_path, {**value, "slices": []})


def test_atomic_write_preserves_existing_file_when_replace_fails(tmp_path, monkeypatch):
    path = branch_state.write_lifecycle(tmp_path, lifecycle())
    original = path.read_text(encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(branch_state.os, "replace", fail_replace)
    changed = lifecycle()
    changed["source_head"] = "e" * 40

    with pytest.raises(OSError, match="replace failed"):
        branch_state.write_lifecycle(tmp_path, changed)

    assert path.read_text(encoding="utf-8") == original
    assert not list(path.parent.glob("*.tmp"))
