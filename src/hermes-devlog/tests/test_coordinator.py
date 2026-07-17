# ruff: noqa: F401
import copy
import json
import os
from multiprocessing import get_context

import pytest

from hermes_devlog.cli import main
from hermes_devlog.errors import CoordinatorError
from hermes_devlog.service import (
    activate,
    add_dependency,
    add_goal,
    complete,
    gate,
    next_action,
    phase,
    question,
    review,
    set_goal_disposition,
)
from hermes_devlog.store import StateStore


def _race_mutation(home, results):
    os.environ["HERMES_HOME"] = str(home)
    try:
        StateStore.from_goal("demo-goal").set_next_action("race", 1)
    except CoordinatorError as error:
        results.put(error.code)
    else:
        results.put("ok")


def template():
    return {
        "release": "v1.0.0",
        "commit": "a" * 40,
        "manifest_hash": "b" * 64,
        "snapshot": "snapshots/demo",
    }


def payload():
    return {
        "goal_id": "demo-goal",
        "title": "Demo goal",
        "template": template(),
        "profile": {"name": "native", "match": "native", "sources": []},
        "route": {"model": "model", "variant": "high"},
        "permissions": {"implement": True, "merge": False},
        "repositories": ["org/demo"],
        "source_bindings": {"issue": "#1", "spec": "#4"},
        "completion_contract": {"final_verification": True},
    }


def running_phase(goal_id, revision=1):
    phase(
        goal_id,
        {
            "phase": "plan",
            "owner": "planner",
            "attempt": 1,
            "work_item_id": goal_id,
            "worker_role": "planner",
            "model": "model",
            "variant": "high",
            "session_id": "s",
            "process_id": "p",
            "command": "plan",
            "worktree": "/worktree",
            "expected_evidence": "plan",
            "observed_evidence": "plan",
            "next_action": "plan",
            "status": "running",
        },
        revision,
    )


def test_invalid_activation_does_not_create_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    invalid = copy.deepcopy(payload())
    invalid["api_token"] = "not allowed"
    with pytest.raises(CoordinatorError) as error:
        activate(invalid)
    assert error.value.code in {"unknown_field", "secret_field"}
    assert not (tmp_path / "dev-log" / "demo-goal").exists()


def test_failed_activation_write_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = StateStore.from_goal("demo-goal")
    original_atomic_json = StateStore._atomic_json
    failed = False

    def fail_state_write(self, path, value):
        nonlocal failed
        if path == self.state_path and not failed:
            failed = True
            raise OSError("injected state write failure")
        return original_atomic_json(self, path, value)

    monkeypatch.setattr(StateStore, "_atomic_json", fail_state_write)
    with pytest.raises(OSError):
        activate(payload())

    assert not store.config_path.exists()
    assert not store.state_path.exists()
    assert activate(payload())["state"]["revision"] == 1


def test_failed_activation_activity_append_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    original = StateStore._activity

    def fail_after_append(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise OSError("injected activity failure")

    monkeypatch.setattr(StateStore, "_activity", fail_after_append)
    with pytest.raises(OSError):
        activate(payload())

    root = tmp_path / "dev-log" / "demo-goal"
    assert not (root / "config.json").exists()
    assert not (root / "state.json").exists()
    assert not (root / "activity.jsonl").exists()


def test_stale_revision_is_rejected_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    result = activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    with pytest.raises(CoordinatorError) as error:
        add_goal(
            "demo-goal", {"id": "other", "title": "Other"}, result["state"]["revision"]
        )
    assert error.value.code == "revision_conflict"
    assert (
        "other" not in StateStore.from_goal("demo-goal").read()["goal_graph"]["nodes"]
    )


def test_dependency_cycle_and_policy_broadening_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "a", "title": "A"}, 1)
    add_goal("demo-goal", {"id": "b", "title": "B"}, 2)
    add_dependency("demo-goal", "a", "b", 3)
    with pytest.raises(CoordinatorError) as error:
        add_dependency("demo-goal", "b", "a", 4)
    assert error.value.code == "dependency_cycle"


def test_review_drift_is_invalidated_and_phase_requires_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {"phase": "implement"}, 1)
    assert error.value.code == "missing_owner"
    review("demo-goal", {"head": "h1", "base": "b1", "diff": "d1", "findings": []}, 1)
    state = review(
        "demo-goal", {"head": "h2", "base": "b1", "diff": "d1", "findings": []}, 2
    )
    assert state["state"]["reviews"][0]["valid"] is False


def test_implementation_requires_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["permissions"]["implement"] = False
    activate(data)
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 1)
    phase(
        "demo-goal",
        {**phase_data, "phase": "plan_review", "attempt": 2},
        2,
    )
    before = StateStore.from_goal("demo-goal").read()

    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "phase": "implement", "attempt": 3}, 3)

    assert error.value.code == "implementation_not_authorized"
    assert StateStore.from_goal("demo-goal").read() == before


def test_sensitive_question_cannot_resume_without_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    running_phase("demo-goal")
    question(
        "demo-goal",
        {"session_id": "s", "question": "May I expand scope?", "answer": "yes"},
        2,
    )
    before = StateStore.from_goal("demo-goal").read()

    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo-goal",
            {
                "phase": "plan",
                "owner": "planner",
                "attempt": 1,
                "work_item_id": "demo-goal",
                "worker_role": "planner",
                "model": "model",
                "variant": "high",
                "session_id": "s",
                "process_id": "p",
                "command": "plan",
                "worktree": "/worktree",
                "expected_evidence": "plan",
                "observed_evidence": "plan",
                "next_action": "plan",
                "status": "completed",
            },
            3,
        )

    assert error.value.code == "question_unresolved"
    assert StateStore.from_goal("demo-goal").read() == before


def test_independent_child_phase_lifecycles(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child-a", "title": "A"}, 1)
    add_goal("demo-goal", {"id": "child-b", "title": "B"}, 2)
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "child-a",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "a-session",
        "process_id": "a-process",
        "command": "plan",
        "worktree": "/worktree-a",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement-a",
    }
    phase("demo-goal", phase_data, 3)
    phase_data.update(
        {
            "work_item_id": "child-b",
            "session_id": "b-session",
            "process_id": "b-process",
            "worktree": "/worktree-b",
            "next_action": "implement-b",
        }
    )
    result = phase("demo-goal", phase_data, 4)

    assert result["state"]["work_items"]["child-a"] == {
        "phase": "plan",
        "next_action": "implement-a",
    }
    assert result["state"]["work_items"]["child-b"] == {
        "phase": "plan",
        "next_action": "implement-b",
    }
    assert next_action("demo-goal")["next_action"] == "implement-a"
    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "work_item_id": "missing"}, 5)
    assert error.value.code == "missing_work_item"


def test_completion_requires_clean_review_children_and_dependencies(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    add_dependency("demo-goal", "child", "demo-goal", 2)

    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 3)
    phase_data.update({"phase": "plan_review", "attempt": 2})
    phase("demo-goal", phase_data, 4)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase("demo-goal", phase_data, 5)
    phase_data.update({"phase": "implementation_review", "attempt": 4})
    phase("demo-goal", phase_data, 6)
    review(
        "demo-goal",
        {"head": "h", "base": "b", "diff": "d", "findings": ["open"]},
        7,
    )
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 8)
    assert error.value.code == "incomplete_workflow"

    phase_data.update({"phase": "remediation", "attempt": 5})
    phase("demo-goal", phase_data, 8)
    phase_data.update({"phase": "implementation_review", "attempt": 6})
    phase("demo-goal", phase_data, 9)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 10)
    phase_data.update({"phase": "pr_delivery", "attempt": 7})
    phase("demo-goal", phase_data, 11)
    phase_data.update({"phase": "final_verification", "attempt": 8})
    phase("demo-goal", phase_data, 12)
    gate("demo-goal", "final_verification", True, 13)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 14)
    assert error.value.code == "incomplete_children"
    assert StateStore.from_goal("demo-goal").read()["completion"]["terminal"] is False


def test_completion_requires_implementation_review_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    gate("demo-goal", "final_verification", False, 1)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 2)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 3)
    assert error.value.code == "incomplete_workflow"


def test_phase_requires_a_complete_resume_record(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {"phase": "plan", "owner": "planner"}, 1)
    assert error.value.code == "incomplete_phase_run"


def test_child_policy_cannot_broaden_merge_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    with pytest.raises(CoordinatorError) as error:
        add_goal(
            "demo-goal",
            {"id": "child", "title": "Child", "policy": {"merge": True}},
            1,
        )
    assert error.value.code == "policy_broadening"


def test_merge_permission_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 1)
    phase_data.update({"phase": "plan_review", "attempt": 2})
    phase("demo-goal", phase_data, 2)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase("demo-goal", phase_data, 3)
    phase_data.update({"phase": "implementation_review", "attempt": 4})
    phase("demo-goal", phase_data, 4)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 5)
    phase_data.update({"phase": "pr_delivery", "attempt": 5})
    phase("demo-goal", phase_data, 6)
    phase_data.update({"phase": "final_verification", "attempt": 6})
    phase("demo-goal", phase_data, 7)
    gate("demo-goal", "final_verification", True, 8)

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 9)

    assert error.value.code == "merge_not_authorized"
    assert StateStore.from_goal("demo-goal").read()["phase"] != "merge_ready"


def test_child_policy_inherits(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["policy"] = {"notifications": False}
    activate(data)

    result = add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)

    assert result["state"]["goal_graph"]["nodes"]["child"]["policy"] == {
        "capacity": 1,
        "notifications": False,
        "merge": False,
        "discovered_work": True,
    }

def test_failed_mutation_activity_append_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    state_before = store.state_path.read_bytes()
    activity_before = store.activity_path.read_bytes()
    original = StateStore._activity

    def fail_after_append(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise OSError("injected activity failure")

    monkeypatch.setattr(StateStore, "_activity", fail_after_append)
    with pytest.raises(OSError):
        store.set_next_action("changed", expected_revision=1)

    assert store.state_path.read_bytes() == state_before
    assert store.activity_path.read_bytes() == activity_before
