# ruff: noqa: F401
import copy
import json
import math

import pytest

from hermes_devlog import service
from hermes_devlog.cli import main
from hermes_devlog.custom_tool import hermes_devlog
from hermes_devlog.errors import CoordinatorError
from hermes_devlog.models import Checkpoint, Phase, ReviewBinding
from hermes_devlog.service import (
    activate,
    add_dependency,
    add_goal,
    complete,
    discovered_work,
    gate,
    phase,
    question,
    review,
    status,
)
from hermes_devlog.validation import (
    activation_payload,
    expected_revision,
    identifier,
    integration_gate,
    json_value,
    reject_secrets,
    strict_mapping,
    validate_state,
)


def activation(goal_id="demo", *, merge=False):
    return {
        "goal_id": goal_id,
        "title": "Demo",
        "template": {
            "release": "v1",
            "commit": "a" * 40,
            "manifest_hash": "b" * 64,
            "snapshot": "snapshots/demo",
        },
        "profile": {"name": "fallback", "match": "fallback", "sources": []},
        "route": {"model": "model", "variant": "high"},
        "permissions": {"implement": True, "merge": merge},
        "policy": {"merge": merge},
        "repositories": ["org/demo"],
        "source_bindings": {"issue": "#1", "spec": "#4"},
        "completion_contract": {"final_verification": True},
    }


def running_phase(goal_id="demo", revision=1):
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


def test_gate_rejects_secret_values_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()
    activity_before = store.activity_path.read_text()

    with pytest.raises(CoordinatorError) as error:
        service.gate("demo", "integration", {"api_token": "x"}, 1)

    assert error.value.code == "secret_field"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_discovered_work_rejects_secret_input_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()
    activity_before = store.activity_path.read_text()

    with pytest.raises(CoordinatorError) as error:
        discovered_work("demo", {"id": "api_token", "title": "x"}, 1)

    assert error.value.code in {"secret_field", "secret_value"}
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_next_does_not_mutate_without_expected_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()

    result = service.next_action("demo")

    assert result["revision"] == before["revision"]
    assert store.read() == before


def test_cli_rejects_malformed_nested_phase_payload(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    assert (
        main(
            [
                "phase",
                json.dumps({"goal_id": "demo", "data": [], "expected_revision": 1}),
            ]
        )
        == 1
    )

    result = json.loads(capsys.readouterr().err)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_object"


def test_cli_and_custom_tool_dispose_child_goal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    payload = {
        "goal_id": "demo",
        "child_id": "child",
        "disposition": "deferred",
        "expected_revision": 2,
    }

    assert main(["goal_disposition", json.dumps(payload)]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["state"]["goal_graph"]["nodes"]["child"]["disposition"] == (
        "deferred"
    )

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "tool"))
    activate(activation())
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    tool_result = hermes_devlog("goal_disposition", payload)
    assert tool_result["ok"] is True
    assert tool_result["state"]["goal_graph"]["nodes"]["child"]["disposition"] == (
        "deferred"
    )


def test_unsupported_state_version_is_not_migrated(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    store = status("demo")
    assert store["state"]["schema_version"] == 1
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["schema_version"] = 99
    path.write_text(json.dumps(state))
    with pytest.raises(CoordinatorError) as error:
        status("demo")
    assert error.value.code == "unsupported_version"


def test_unknown_persisted_state_field_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["unexpected"] = True
    path.write_text(json.dumps(state))
    with pytest.raises(CoordinatorError) as error:
        status("demo")
    assert error.value.code == "unknown_field"


@pytest.mark.parametrize("topology", ["orphan", "cycle", "multiple_roots"])
def test_containment_topology_is_validated(topology, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    if topology != "orphan":
        add_goal("demo", {"id": "child", "title": "Child"}, 1)
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    nodes = state["goal_graph"]["nodes"]
    if topology == "orphan":
        nodes["demo"]["parent_id"] = "missing"
    elif topology == "cycle":
        nodes["demo"]["parent_id"] = "child"
        nodes["child"]["parent_id"] = "demo"
    else:
        nodes["child"]["parent_id"] = None
    path.write_text(json.dumps(state))

    with pytest.raises(CoordinatorError) as error:
        status("demo")

    assert error.value.code == "invalid_state"


def test_service_rejects_invalid_graphs_and_records_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    with pytest.raises(CoordinatorError):
        add_goal("demo", {"id": "child", "title": "Child", "parent_id": "missing"}, 1)
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    with pytest.raises(CoordinatorError):
        add_goal("demo", {"id": "child", "title": "Child"}, 2)
    add_dependency("demo", "child", "demo", 2)
    with pytest.raises(CoordinatorError):
        add_dependency("demo", "child", "demo", 3)
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo",
        "worker_role": "planner",
        "model": "model",
        "variant": "high",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan-record",
        "observed_evidence": "plan-record",
        "next_action": "plan",
    }
    phase("demo", phase_data, 3)
    phase_data.update({"phase": "plan_review", "attempt": 2})
    phase("demo", phase_data, 4)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase_data["next_action"] = "implement"
    phase_data["status"] = "running"
    phase("demo", phase_data, 5)
    with pytest.raises(CoordinatorError):
        phase("demo", {"phase": "issue", "owner": "builder"}, 6)
    review("demo", {"head": "h", "base": "b", "diff": "d", "findings": ["one"]}, 6)
    question(
        "demo",
        {"session_id": "s", "question": "which file?", "answer": "the package"},
        7,
    )
    assert Checkpoint(Phase.PLAN, "plan").next_action == "plan"
    assert ReviewBinding("h", "b", "d").head == "h"


def test_cli_dispatches_read_and_mutating_operations(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert main(["activate", json.dumps(activation())]) == 0
    capsys.readouterr()
    commands = [
        ("status", {"goal_id": "demo"}),
        ("next", {"goal_id": "demo"}),
        (
            "goal",
            {
                "goal_id": "demo",
                "node": {"id": "child", "title": "Child"},
                "expected_revision": 1,
            },
        ),
        (
            "gate",
            {
                "goal_id": "demo",
                "name": "final_verification",
                "value": False,
                "expected_revision": 2,
            },
        ),
    ]
    for operation, payload in commands:
        assert main([operation, json.dumps(payload)]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["ok"] is True


def test_custom_tool_returns_structured_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    result = hermes_devlog("status", {"goal_id": "missing"})
    assert result["ok"] is False
    assert hermes_devlog("not-supported", {})["error"]["code"] == (
        "unsupported_operation"
    )
