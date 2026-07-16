import copy

import pytest

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
    }


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

    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 8)
    with pytest.raises(CoordinatorError) as error:
        complete("demo-goal", 9)
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


def test_sensitive_question_always_needs_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    result = question(
        "demo-goal",
        {"session_id": "s", "question": "May I merge this PR?", "answer": "yes"},
        1,
    )
    assert result["state"]["questions"][-1]["status"] == "needs_user"


def test_next_action_selects_ready_child(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    add_goal("demo-goal", {"id": "child", "title": "Child"}, 1)
    result = next_action("demo-goal")
    assert result["next_action"] == "begin_child:child"
