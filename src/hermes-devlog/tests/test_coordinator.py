import copy
import json

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
        "route": {"model": "openai/gpt-5.6-luna", "variant": "high"},
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
    phase_data["phase"] = "implement"
    phase_data["next_action"] = "implementation_review"
    phase("demo-goal", phase_data, 4)
    phase_data["phase"] = "implementation_review"
    phase_data["next_action"] = "verify"
    phase("demo-goal", phase_data, 5)

    gate("demo-goal", "final_verification", True, 6)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 7)
    assert error.value.code == "stale_review"

    review(
        "demo-goal",
        {"head": "h", "base": "b", "diff": "d", "findings": ["open"]},
        7,
    )
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 8)
    assert error.value.code == "stale_review"

    phase_data["phase"] = "remediation"
    phase_data["next_action"] = "implementation_review"
    phase("demo-goal", phase_data, 8)
    phase_data["phase"] = "implementation_review"
    phase_data["next_action"] = "verify"
    phase("demo-goal", phase_data, 9)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 10)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 11)
    assert error.value.code == "incomplete_children"
    assert StateStore.from_goal("demo-goal").read()["completion"]["terminal"] is False


def test_completion_requires_implementation_review_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    gate("demo-goal", "final_verification", True, 1)
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
    phase_data["phase"] = "implement"
    phase_data["next_action"] = "implementation_review"
    phase("demo-goal", phase_data, 2)
    phase_data["phase"] = "implementation_review"
    phase_data["next_action"] = "verify"
    phase("demo-goal", phase_data, 3)
    gate("demo-goal", "final_verification", True, 4)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 5)

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 6)

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
        "model": "openai/gpt-5.6-luna",
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
    assert result["state"]["phase_runs"][-1]["model"] == "openai/gpt-5.6-luna"
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
    phase_data.update({"phase": "implement", "next_action": "implementation_review"})
    phase("demo-goal", phase_data, 2)
    phase_data.update({"phase": "remediation", "next_action": "implementation_review"})
    phase("demo-goal", phase_data, 3)
    gate("demo-goal", "final_verification", True, 4)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 5)

    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 6)

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
    phase_data.update({"phase": "implement", "next_action": "review"})
    phase("demo-goal", phase_data, 2)
    phase_data.update({"phase": "implementation_review", "next_action": "verify"})
    phase("demo-goal", phase_data, 3)
    gate("demo-goal", "final_verification", True, 4)
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
        {"session_id": "s1", "question": "which file?", "answer": "service.py"},
        2,
    )

    assert result["state"]["phase_runs"][-1]["question_status"] == "answered"


def test_phase_run_question_escalation_updates_active_session(tmp_path, monkeypatch):
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

    result = question(
        "demo-goal",
        {"session_id": "s1", "question": "May I expand scope?", "answer": "yes"},
        2,
    )

    assert result["state"]["phase_runs"][-1]["question_status"] == "needs_user"


@pytest.mark.parametrize("session_id", ["missing", "finished"])
def test_question_requires_running_session(tmp_path, monkeypatch, session_id):
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
        "session_id": "running",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "running",
    }
    phase("demo-goal", phase_data, 1)
    if session_id == "finished":
        phase_data["status"] = "completed"
        phase("demo-goal", phase_data, 2)
        revision = 3
    else:
        revision = 2
    store = StateStore.from_goal("demo-goal")
    before = store.read()

    with pytest.raises(CoordinatorError) as error:
        question(
            "demo-goal", {"session_id": session_id, "question": "which file?"}, revision
        )

    assert error.value.code == "invalid_session"
    assert store.read() == before


@pytest.mark.parametrize(
    ("node", "code"),
    [
        ([], "invalid_object"),
        ({"id": "child", "title": "Child", "source_bindings": {}}, "invalid_binding"),
        (
            {
                "id": "child",
                "title": "Child",
                "completion_contract": {},
            },
            "invalid_binding",
        ),
        (
            {
                "id": "child",
                "title": "Child",
                "contract": {},
                "completion_contract": {"done": True},
            },
            "invalid_binding",
        ),
    ],
)
def test_child_goal_bindings_are_strictly_validated(tmp_path, monkeypatch, node, code):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())

    with pytest.raises(CoordinatorError) as error:
        add_goal("demo-goal", node, 1)

    assert error.value.code == code


def test_goal_and_dependency_errors_are_structured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    with pytest.raises(CoordinatorError) as error:
        add_goal("demo-goal", {"id": "child", "title": "Child", "policy": []}, 1)
    assert error.value.code == "invalid_object"
    with pytest.raises(CoordinatorError) as error:
        add_dependency("demo-goal", "missing", "demo-goal", 1)
    assert error.value.code == "missing_goal"
    with pytest.raises(CoordinatorError) as error:
        set_goal_disposition("demo-goal", "missing", "resolved", 1)
    assert error.value.code == "missing_goal"


def test_store_rejects_duplicate_and_supports_scheduler_checkpoint(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    with pytest.raises(CoordinatorError) as error:
        activate(payload())
    assert error.value.code == "already_exists"
    assert store.set_next_action("resume")["next_action"] == "resume"
    assert store.set_next_action("resume")["revision"] == 2


def test_store_rejects_malformed_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    store.config_path.write_text("{")
    with pytest.raises(CoordinatorError) as error:
        store.read_config()
    assert error.value.code == "invalid_state"
    store.config_path.write_text(json.dumps({"schema_version": 99}))
    with pytest.raises(CoordinatorError) as error:
        store.read_config()
    assert error.value.code == "invalid_state"


def test_cli_dispatches_remaining_operations(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert main(["activate", json.dumps(payload())]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "goal",
                json.dumps(
                    {
                        "goal_id": "demo-goal",
                        "node": {"id": "child", "title": "Child"},
                        "expected_revision": 1,
                    }
                ),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "dependency",
                json.dumps(
                    {
                        "goal_id": "demo-goal",
                        "blocker": "demo-goal",
                        "blocked": "child",
                        "expected_revision": 2,
                    }
                ),
            ]
        )
        == 0
    )
    capsys.readouterr()
    phase_data = {
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
        "next_action": "plan",
    }
    assert (
        main(
            [
                "phase",
                json.dumps(
                    {"goal_id": "demo-goal", "data": phase_data, "expected_revision": 3}
                ),
            ]
        )
        == 0
    )
    capsys.readouterr()
    for operation, data, revision in [
        (
            "review",
            {"head": "h", "base": "b", "diff": "d", "findings": []},
            4,
        ),
        (
            "question",
            {"session_id": "s", "question": "which file?", "answer": "x"},
            5,
        ),
        ("complete", None, 6),
        ("gate", {"name": "final_verification", "value": True}, 6),
        (
            "discovered_work",
            {"item": {"id": "bug", "title": "bug"}},
            7,
        ),
    ]:
        envelope = {"goal_id": "demo-goal", "expected_revision": revision}
        if operation == "complete":
            pass
        elif operation == "gate":
            envelope.update(data)
        else:
            envelope["data" if operation in {"review", "question"} else "item"] = (
                data if operation != "discovered_work" else data["item"]
            )
        assert main([operation, json.dumps(envelope)]) in {0, 1}
        capsys.readouterr()
