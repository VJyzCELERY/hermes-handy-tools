# ruff: noqa: F401
import copy
import json
import os
from multiprocessing import get_context
from queue import Empty

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
    status,
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


def _blocked_mutation(home, replaced, release, results):
    os.environ["HERMES_HOME"] = str(home)
    store = StateStore.from_goal("demo-goal")
    original_activity = StateStore._activity

    def block_activity(self, *args, **kwargs):
        replaced.set()
        release.wait(2)
        return original_activity(self, *args, **kwargs)

    StateStore._activity = block_activity
    try:
        store.set_next_action("race", 1)
    except Exception as error:  # pragma: no cover - child-process reporting
        results.put(("writer_error", type(error).__name__))
    else:
        results.put(("writer", "ok"))


def _read_during_mutation(home, started, done, results):
    os.environ["HERMES_HOME"] = str(home)
    started.set()
    try:
        results.put(("reader", StateStore.from_goal("demo-goal").read()["revision"]))
    except CoordinatorError as error:
        results.put(("reader_error", error.code))
    finally:
        done.set()


def _crash_after_state_replacement(home):
    os.environ["HERMES_HOME"] = str(home)
    original_atomic_json = StateStore._atomic_json

    def write_then_crash(store, path, value):
        original_atomic_json(store, path, value)
        if path == store.state_path:
            os._exit(17)

    StateStore._atomic_json = write_then_crash
    activate(payload())


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
        "routes": {
            "planner": {"model": "model", "reasoning": "high", "agent": "opencode"},
            "reviewer": {"model": "model", "reasoning": "high", "agent": "opencode"},
            "worker": {"model": "model", "reasoning": "high", "agent": "opencode"},
        },
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
            "reasoning": "high", "agent": "opencode",
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


def test_interrupted_activation_is_recovered(tmp_path, monkeypatch):
    context = get_context("fork")
    process = context.Process(target=_crash_after_state_replacement, args=(tmp_path,))
    process.start()
    process.join(2)
    assert process.exitcode == 17

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert status("demo-goal")["state"]["revision"] == 1


def test_implementation_review_rejects_builder_session(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    run = {
        "owner": "worker",
        "work_item_id": "demo-goal",
        "worker_role": "worker",
        "model": "model",
        "reasoning": "high", "agent": "opencode",
        "session_id": "shared",
        "process_id": "p",
        "command": "run",
        "worktree": "/worktree",
        "expected_evidence": "e",
        "observed_evidence": "e",
        "next_action": "next",
    }
    phase("demo-goal", {**run, "phase": "plan", "attempt": 1}, 1)
    phase(
        "demo-goal",
        {
            **run,
            "phase": "implement",
            "attempt": 2,
            "worker_role": "reviewer",
            "session_id": "plan-review-session",
            "process_id": "plan-review-process",
        },
        2,
    )
    phase("demo-goal", {**run, "phase": "implement", "attempt": 3}, 3)

    with pytest.raises(CoordinatorError):
        phase(
            "demo-goal",
            {**run, "phase": "implementation_review", "attempt": 4},
            4,
        )


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
        "reasoning": "high", "agent": "opencode",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 1)
    before = StateStore.from_goal("demo-goal").read()

    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "phase": "implement", "attempt": 2}, 2)

    assert error.value.code == "implementation_not_authorized"
    assert StateStore.from_goal("demo-goal").read() == before


def test_child_implementation_permission_narrows(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal(
        "demo-goal",
        {"id": "child", "title": "Child", "permissions": {"implement": False}},
        1,
    )
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "child",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high", "agent": "opencode",
        "session_id": "child-session",
        "process_id": "child-process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 2)
    before = StateStore.from_goal("demo-goal").read()

    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo-goal",
            {**phase_data, "phase": "implement", "attempt": 2},
            3,
        )

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
                "reasoning": "high", "agent": "opencode",
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
        "reasoning": "high", "agent": "opencode",
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


def test_phase_identity_cannot_cross_work_items(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high", "agent": "opencode",
        "session_id": "shared",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "running",
    }
    phase("demo-goal", phase_data, 2)
    before = StateStore.from_goal("demo-goal").read()

    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "work_item_id": "child"}, 3)

    assert error.value.code == "invalid_phase_run"
    assert StateStore.from_goal("demo-goal").read() == before


def test_completed_goal_rejects_all_mutations(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")

    def mark_terminal(state):
        state["completion"]["ready"] = True
        state["completion"]["terminal"] = True
        state["phase"] = "merge_ready"
        return state

    store.mutate(1, "complete", mark_terminal)
    before = store.read()
    activity_before = store.activity_path.read_bytes()

    with pytest.raises(CoordinatorError) as error:
        add_goal("demo-goal", {"id": "child", "title": "Child"}, 2)

    assert error.value.code == "terminal_state"
    assert store.read() == before
    assert store.activity_path.read_bytes() == activity_before


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
        "reasoning": "high", "agent": "opencode",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 3)
    phase_data.update(
        {
            "phase": "implement",
            "attempt": 2,
            "worker_role": "reviewer",
            "session_id": "plan-review-session",
            "process_id": "plan-review-process",
        }
    )
    phase("demo-goal", phase_data, 4)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase("demo-goal", phase_data, 5)
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 4,
            "worker_role": "reviewer",
            "session_id": "review-session",
            "process_id": "review-process",
        }
    )
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
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 6,
            "session_id": "review-session-2",
            "process_id": "review-process-2",
        }
    )
    phase("demo-goal", phase_data, 9)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 10)
    phase_data.update({"phase": "pr_delivery", "attempt": 7})
    phase("demo-goal", phase_data, 11)
    phase_data.update({"phase": "final_verification", "attempt": 8})
    phase("demo-goal", phase_data, 12)
    gate("demo-goal", "final_verification", True, 13)
    set_goal_disposition("demo-goal", "child", "resolved", 14)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 15)
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


def test_final_verification_can_enter_remediation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high", "agent": "opencode",
        "session_id": "plan-session",
        "process_id": "plan-process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "continue",
    }
    phase("demo-goal", phase_data, 1)
    phase_data.update(
        {
            "phase": "implement",
            "attempt": 2,
            "worker_role": "reviewer",
            "session_id": "plan-review-session",
            "process_id": "plan-review-process",
        }
    )
    phase("demo-goal", phase_data, 2)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase("demo-goal", phase_data, 3)
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 4,
            "session_id": "implementation-review-session",
            "process_id": "implementation-review-process",
        }
    )
    phase("demo-goal", phase_data, 4)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 5)
    phase_data.update({"phase": "pr_delivery", "attempt": 5})
    phase("demo-goal", phase_data, 6)
    phase_data.update({"phase": "final_verification", "attempt": 6})
    phase("demo-goal", phase_data, 7)
    gate("demo-goal", "final_verification", True, 8)

    result = phase(
        "demo-goal",
        {**phase_data, "phase": "remediation", "attempt": 7},
        9,
    )

    assert result["state"]["phase"] == "remediation"
    assert result["state"]["gates"]["final_verification"] is False
    assert result["state"]["reviews"][0]["valid"] is False


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
        "reasoning": "high", "agent": "opencode",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", phase_data, 1)
    phase_data.update(
        {
            "phase": "implement",
            "attempt": 2,
            "worker_role": "reviewer",
            "session_id": "plan-review-session",
            "process_id": "plan-review-process",
        }
    )
    phase("demo-goal", phase_data, 2)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase("demo-goal", phase_data, 3)
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 4,
            "worker_role": "reviewer",
            "session_id": "review-session",
            "process_id": "review-process",
        }
    )
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

def test_failed_mutation_activity_append_recovers_completed_commit(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    original = StateStore._activity

    def fail_after_append(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise OSError("injected activity failure")

    monkeypatch.setattr(StateStore, "_activity", fail_after_append)
    with pytest.raises(OSError):
        store.set_next_action("changed", expected_revision=1)

    assert store.pending_path.exists()
    assert store.read()["revision"] == 2
    assert store.read()["next_action"] == "changed"
    assert not store.pending_path.exists()


def test_failed_mutation_activity_append_recovers_pending_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")

    def fail_before_append(self, *args, **kwargs):
        raise OSError("injected activity failure")

    monkeypatch.setattr(StateStore, "_activity", fail_before_append)
    with pytest.raises(OSError):
        store.set_next_action("changed", expected_revision=1)

    assert store.read()["revision"] == 2
    assert store.read()["next_action"] == "changed"
    assert not store.pending_path.exists()


def test_concurrent_read_returns_consistent_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    context = get_context("fork")
    replaced = context.Event()
    release = context.Event()
    started = context.Event()
    done = context.Event()
    results = context.Queue()
    writer = context.Process(
        target=_blocked_mutation,
        args=(tmp_path, replaced, release, results),
    )
    reader = context.Process(
        target=_read_during_mutation,
        args=(tmp_path, started, done, results),
    )
    writer.start()
    assert replaced.wait(2)
    reader.start()
    assert started.wait(2)
    assert not done.wait(0.2)
    release.set()
    writer.join(2)
    reader.join(2)
    assert not writer.is_alive()
    assert not reader.is_alive()
    # note: writer and reader enqueue independently after release; their
    # arrival order is nondeterministic, so compare as a set, not a sequence.
    drained = {results.get(timeout=2), results.get(timeout=2)}
    assert drained == {("writer", "ok"), ("reader", 2)}
    with pytest.raises(Empty):
        results.get_nowait()


def test_distinct_role_routes_are_pinned_and_mismatch_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["routes"] = {
        "planner": {"model": "gpt-5.6-terra", "reasoning": "high", "agent": "opencode"},
        "reviewer": {
            "model": "gpt-5.6-terra", "reasoning": "high", "agent": "opencode"
        },
        "worker": {"model": "gpt-5.6-luna", "reasoning": "high", "agent": "opencode"},
    }
    activate(data)
    config = StateStore.from_goal("demo-goal").read_config()
    assert config["routes"]["worker"]["model"] == "gpt-5.6-luna"
    assert config["routes"]["planner"]["model"] == "gpt-5.6-terra"

    plan_run = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "gpt-5.6-terra",
        "reasoning": "high", "agent": "opencode",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
    }
    phase("demo-goal", plan_run, 1)

    # A worker using the planner's route is a route mismatch.
    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo-goal",
            {
                **plan_run,
                "phase": "implement",
                "attempt": 2,
                "worker_role": "worker",
                "model": "gpt-5.6-terra",
                "reasoning": "high", "agent": "opencode",
            },
            2,
        )
    assert error.value.code == "route_mismatch"


def test_routes_default_agents_allow_role_specific_agents_and_skip_implement(
    tmp_path, monkeypatch
):
    """New goals pin agent routes and move directly from plan to implementation."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()

    data["routes"] = {
        "planner": {"model": "gpt-5.6-terra", "reasoning": "high"},
        "reviewer": {
            "model": "gpt-5.6-terra",
            "reasoning": "high",
            "agent": "codex",
        },
        "worker": {
            "model": "gpt-5.6-luna",
            "reasoning": "high",
            "agent": "claude-code",
        },
    }
    activate(data)
    config = StateStore.from_goal("demo-goal").read_config()
    assert config["routes"]["planner"]["agent"] == "opencode"
    assert config["routes"]["reviewer"]["agent"] == "codex"
    assert config["routes"]["worker"]["agent"] == "claude-code"

    plan_run = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "gpt-5.6-terra",
        "reasoning": "high",
        "agent": "opencode",
        "session_id": "plan-session",
        "process_id": "plan-process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }
    phase("demo-goal", plan_run, 1)

    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo-goal",
            {
                **plan_run,
                "phase": "implement",
                "attempt": 2,
                "worker_role": "worker",
                "model": "gpt-5.6-luna",
                "agent": "opencode",
            },
            2,
        )
    assert error.value.code == "route_mismatch"

    state = phase(
        "demo-goal",
        {
            **plan_run,
            "phase": "implement",
            "attempt": 2,
            "worker_role": "worker",
            "model": "gpt-5.6-luna",
            "agent": "claude-code",
            "session_id": "implementation-session",
            "process_id": "implementation-process",
            "command": "implement",
            "next_action": "implementation_review",
        },
        2,
    )
    assert state["state"]["phase"] == "implement"
