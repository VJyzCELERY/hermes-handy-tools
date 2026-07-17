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


def test_scheduler_requires_expected_revision(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    with pytest.raises(CoordinatorError) as error:
        activate(payload())
    assert error.value.code == "already_exists"
    assert (
        store.set_next_action("resume", expected_revision=1)["next_action"]
        == "resume"
    )
    assert store.set_next_action("resume", expected_revision=2)["revision"] == 3
    before = store.read()
    activity_before = store.activity_path.read_text()

    with pytest.raises(CoordinatorError) as error:
        store.set_next_action("stale", expected_revision=1)

    assert error.value.code == "revision_conflict"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before




def test_required_workflow_phases_are_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = payload()
    data["permissions"]["merge"] = True
    data["policy"] = {"merge": True}
    activate(data)
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
        "next_action": "plan-review",
    }
    phase("demo-goal", phase_data, 1)
    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", {**phase_data, "phase": "implement", "attempt": 2}, 2)
    assert error.value.code == "invalid_transition"
    for revision, phase_name in enumerate(
        ("plan_review", "implement", "implementation_review"), start=2
    ):
        phase_data = {**phase_data, "phase": phase_name, "attempt": revision}
        phase("demo-goal", phase_data, revision)
    review("demo-goal", {"head": "h", "base": "b", "diff": "d", "findings": []}, 5)
    phase_data = {**phase_data, "phase": "pr_delivery", "attempt": 5}
    phase("demo-goal", phase_data, 6)
    phase_data = {**phase_data, "phase": "final_verification", "attempt": 6}
    phase("demo-goal", phase_data, 7)
    gate("demo-goal", "final_verification", True, 8)
    assert complete("demo-goal", 9)["state"]["completion"]["terminal"] is True


def test_phase_requires_pinned_route(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    data = {
        "phase": "plan",
        "attempt": 1,
        "owner": "planner",
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "other-model",
        "variant": "high",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
    }
    store = StateStore.from_goal("demo-goal")
    before = store.read()
    activity_before = store.activity_path.read_text()
    with pytest.raises(CoordinatorError) as error:
        phase("demo-goal", data, 1)
    assert error.value.code == "route_mismatch"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_completed_phase_releases_capacity(tmp_path, monkeypatch):
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
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
        "status": "running",
    }
    phase("demo-goal", phase_data, 1)
    phase("demo-goal", {**phase_data, "status": "completed"}, 2)
    result = phase(
        "demo-goal",
        {**phase_data, "session_id": "s2", "process_id": "p2"},
        3,
    )
    assert sum(run["status"] == "running" for run in result["state"]["phase_runs"]) == 1
    with pytest.raises(CoordinatorError) as error:
        question("demo-goal", {"session_id": "s", "question": "which file?"}, 4)
    assert error.value.code == "invalid_session"


def test_empty_review_binding_is_rejected_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    store = StateStore.from_goal("demo-goal")
    before = store.read()
    activity_before = store.activity_path.read_text()
    with pytest.raises(CoordinatorError) as error:
        review("demo-goal", {"head": "", "base": "b", "diff": "d", "findings": []}, 1)
    assert error.value.code == "invalid_review"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_child_profile_inherits_and_only_narrows(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    inherited = add_goal("demo-goal", {"id": "inherited", "title": "Inherited"}, 1)
    assert (
        inherited["state"]["goal_graph"]["nodes"]["inherited"]["profile"]
        == payload()["profile"]
    )
    narrowed = add_goal(
        "demo-goal",
        {
            "id": "narrowed",
            "title": "Narrowed",
            "profile": {"name": "fallback", "match": "fallback", "sources": []},
        },
        2,
    )
    assert (
        narrowed["state"]["goal_graph"]["nodes"]["narrowed"]["profile"]["match"]
        == "fallback"
    )
    with pytest.raises(CoordinatorError) as error:
        add_goal(
            "demo-goal",
            {
                "id": "broadened",
                "title": "Broadened",
                "parent_id": "narrowed",
                "profile": {"name": "native", "match": "native", "sources": []},
            },
            3,
        )
    assert error.value.code == "profile_broadening"


def test_concurrent_mutation_allows_one_revision_winner(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(payload())
    context = get_context("fork")
    results = context.Queue()
    processes = [
        context.Process(target=_race_mutation, args=(tmp_path, results))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    outcomes = [results.get(timeout=2) for _ in processes]
    assert sorted(outcomes) == ["ok", "revision_conflict"]
    state = StateStore.from_goal("demo-goal").read()
    assert state["revision"] == 2
    assert (
        len(StateStore.from_goal("demo-goal").activity_path.read_text().splitlines())
        == 2
    )


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
