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
        "routes": {
            "planner": {"model": "model", "variant": "high"},
            "reviewer": {"model": "model", "variant": "high"},
            "worker": {"model": "model", "variant": "high"},
        },
        "harness": "opencode",
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


def test_sensitive_question_always_needs_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    running_phase("demo-goal")
    result = question(
        "demo-goal",
        {"session_id": "s", "question": "May I merge this PR?", "answer": "yes"},
        2,
    )
    assert result["state"]["questions"][-1]["status"] == "needs_user"


def test_next_action_selects_ready_child(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    result = next_action("demo-goal")
    assert result["next_action"] == "begin_child:child"


def test_child_goal_can_transition_to_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)

    result = set_goal_disposition("demo-goal", "child", "resolved", 2)

    assert result["state"]["goal_graph"]["nodes"]["child"]["disposition"] == (
        "resolved"
    )


def test_stacked_review_bindings_remain_current_independently(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    review("demo-goal", {"head": "h", "base": "b1", "diff": "d1", "findings": []}, 1)
    result = review(
        "demo-goal", {"head": "h", "base": "b2", "diff": "d2", "findings": []}, 2
    )

    assert all(item["valid"] for item in result["state"]["reviews"])


def test_review_diff_drift_invalidates_same_base_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    review("demo-goal", {"head": "h", "base": "b", "diff": "d1", "findings": []}, 1)
    result = review(
        "demo-goal", {"head": "h", "base": "b", "diff": "d2", "findings": []}, 2
    )

    assert result["state"]["reviews"][0]["valid"] is False
    assert result["state"]["reviews"][1]["valid"] is True


def test_phase_run_identity_is_required_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
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

    result = phase("demo-goal", data, 1)

    assert result["state"]["phase_runs"][-1]["work_item_id"] == "demo-goal"
    assert result["state"]["phase_runs"][-1]["worker_role"] == "planner"
    assert result["state"]["phase_runs"][-1]["model"] == "model"
    assert result["state"]["phase_runs"][-1]["variant"] == "high"


def test_completion_requires_implementation_review_after_remediation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["permissions"]["merge"] = True
    data["policy"] = {"merge": True}
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
    phase_data.update(
        {
            "phase": "plan_review",
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
    review(
        "demo-goal",
        {"head": "h", "base": "b", "diff": "d", "findings": ["open"]},
        5,
    )
    phase_data.update({"phase": "remediation", "attempt": 5})
    phase("demo-goal", phase_data, 6)
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 6,
            "session_id": "review-session-2",
            "process_id": "review-process-2",
        }
    )
    phase("demo-goal", phase_data, 7)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 8)

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 9)

    assert error.value.code == "incomplete_workflow"


def test_active_phase_runs_respect_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["policy"] = {"capacity": 1}
    activate(data)
    phase_data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s1",
        "process_id": "p1",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "running",
    }
    phase("demo-goal", phase_data, 1)
    before = StateStore.from_goal("demo-goal").read()
    phase_data.update({"session_id": "s2", "process_id": "p2"})

    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", phase_data, 2)

    assert error.value.code == "capacity_exceeded"
    assert StateStore.from_goal("demo-goal").read() == before


def test_active_phase_runs_block_same_work_item_advance(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    running_phase("demo-goal")

    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo-goal",
            {
                "phase": "plan",
                "attempt": 2,
                "owner": "planner",
                "work_item_id": "demo-goal",
                "worker_role": "planner",
                "model": "model",
                "variant": "high",
                "session_id": "s2",
                "process_id": "p2",
                "command": "plan",
                "worktree": "/worktree",
                "expected_evidence": "plan",
                "observed_evidence": "plan",
                "next_action": "plan",
            },
            2,
        )

    assert error.value.code == "active_phase_run"


def test_active_phase_runs_block_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["permissions"]["merge"] = True
    data["policy"] = {"merge": True}
    activate(data)
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    set_goal_disposition("demo-goal", "child", "resolved", 2)

    phase_data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "root-session",
        "process_id": "root-process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "continue",
    }
    for revision, phase_name in enumerate(
        ("plan", "plan_review", "implement", "implementation_review"),
        start=3,
    ):
        phase_data.update(
            {
                "phase": phase_name,
                "attempt": revision - 2,
                **(
                    {
                        "worker_role": "reviewer",
                        "session_id": (
                            "plan-review-session"
                            if phase_name == "plan_review"
                            else "review-session"
                        ),
                        "process_id": (
                            "plan-review-process"
                            if phase_name == "plan_review"
                            else "review-process"
                        ),
                    }
                    if phase_name in {"plan_review", "implementation_review"}
                    else {}
                ),
            }
        )
        phase("demo-goal", phase_data, revision)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 7)
    phase_data.update({"phase": "pr_delivery", "attempt": 5})
    phase("demo-goal", phase_data, 8)
    phase_data.update({"phase": "final_verification", "attempt": 6})
    phase("demo-goal", phase_data, 9)
    gate("demo-goal", "final_verification", True, 10)

    phase(
        "demo-goal",
        {
            **phase_data,
            "phase": "plan",
            "attempt": 1,
            "work_item_id": "child",
            "session_id": "child-session",
            "process_id": "child-process",
            "status": "running",
        },
        11,
    )

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 12)

    assert error.value.code == "active_phase_run"
    assert StateStore.from_goal("demo-goal").read()["completion"]["ready"] is False


def test_completion_requires_remediation_after_review_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["permissions"]["merge"] = True
    data["policy"] = {"merge": True}
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
    phase_data.update(
        {
            "phase": "plan_review",
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
    review(
        "demo-goal",
        {"head": "h", "base": "b", "diff": "d", "findings": ["open"]},
        5,
    )
    review(
        "demo-goal",
        {"head": "h", "base": "b", "diff": "d", "findings": []},
        6,
    )

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 7)

    assert error.value.code == "incomplete_workflow"


def test_child_goal_persists_source_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())

    result = add_goal(
        "demo-goal",
        {
            "id": "child",
            "title": "Child",
            "source_bindings": {"issue": "#2"},
            "completion_contract": {"final_verification": True},
        },
        1,
    )

    child = result["state"]["goal_graph"]["nodes"]["child"]
    assert child["source_bindings"] == {"issue": "#2"}
    assert child["completion_contract"] == {"final_verification": True}


def test_phase_status_releases_and_enforces_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["policy"] = {"capacity": 1}
    activate(data)
    phase_data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s1",
        "process_id": "p1",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "completed",
    }
    phase("demo-goal", phase_data, 1)
    phase_data.update({"session_id": "s2", "process_id": "p2", "status": "running"})
    phase("demo-goal", phase_data, 2)

    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "status": "unknown"}, 3)

    assert error.value.code == "invalid_phase_run"


def test_phase_run_persists_question_status(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    phase_data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s1",
        "process_id": "p1",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "running",
    }
    phase("demo-goal", phase_data, 1)
    assert (
        StateStore.from_goal("demo-goal").read()["phase_runs"][-1]["question_status"]
        == "none"
    )

    result = question(
        "demo-goal",
        {
            "session_id": "s1",
            "question": "which file?",
            "answer": "service.py",
            "authority_reference": "state:policy",
        },
        2,
    )

    assert result["state"]["phase_runs"][-1]["question_status"] == "answered"
