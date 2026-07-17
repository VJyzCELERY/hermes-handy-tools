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
        "routes": {
            "planner": {"model": "model", "reasoning": "high", "agent": "opencode"},
            "reviewer": {"model": "model", "reasoning": "high", "agent": "opencode"},
            "worker": {"model": "model", "reasoning": "high", "agent": "opencode"},
        },
        "permissions": {
            "implement": True,
            "commit": merge,
            "push": merge,
            "create_pr": merge,
            "merge": merge,
        },
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
            "reasoning": "high",
            "agent": "opencode",
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


@pytest.mark.parametrize("value", [None, "bad id", 1])
def test_validation_rejects_invalid_identifiers(value):
    with pytest.raises(CoordinatorError) as error:
        identifier(value, "id")
    assert error.value.code == "invalid_identifier"


def test_validation_rejects_invalid_evidence_values():
    with pytest.raises(CoordinatorError) as error:
        json_value(object(), "evidence")
    assert error.value.code == "invalid_state"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_evidence_rejected(value):
    with pytest.raises(CoordinatorError) as error:
        json_value(value, "evidence")
    assert error.value.code == "invalid_state"
    with pytest.raises(CoordinatorError) as error:
        json_value({1: "value"}, "evidence")
    assert error.value.code == "invalid_state"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"id": "gate"}, "invalid_gate"),
        ({"id": "bad id", "status": "open", "evidence": {}}, "invalid_identifier"),
        ({"id": "gate", "status": "other", "evidence": {}}, "invalid_gate"),
    ],
)
def test_integration_gate_requires_bounded_evidence(value, code):
    with pytest.raises(CoordinatorError) as error:
        integration_gate(value)
    assert error.value.code == code


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("template", {"release": "v1"}),
        (
            "template",
            {
                "release": "v1",
                "commit": "bad",
                "manifest_hash": "b" * 64,
                "snapshot": "snap",
            },
        ),
        (
            "template",
            {
                "release": "v1",
                "commit": "a" * 40,
                "manifest_hash": "bad",
                "snapshot": "snap",
            },
        ),
        ("profile", {"name": "x", "match": "native", "sources": [1]}),
        ("policy", {"notifications": "yes"}),
    ],
)
def test_activation_rejects_malformed_bindings(field, value):
    data = activation()
    data[field] = value
    with pytest.raises(CoordinatorError) as error:
        activation_payload(data)
    assert error.value.code in {"invalid_template", "invalid_profile", "invalid_policy"}


@pytest.mark.parametrize(
    "snapshot",
    [
        "../escape",
        "/absolute",
        "snapshots/../escape",
        "snapshots/./demo",
        "bad\x00path",
    ],
)
def test_malformed_paths_reject_snapshot(snapshot):
    data = activation()
    data["template"]["snapshot"] = snapshot

    with pytest.raises(CoordinatorError) as error:
        activation_payload(data)

    assert error.value.code == "invalid_template"


@pytest.mark.parametrize(
    "worktree", ["relative", "/worktree/../escape", "/bad\x00path"]
)
def test_malformed_paths_reject_worktree(tmp_path, monkeypatch, worktree):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()
    activity_before = store.activity_path.read_text()
    data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high",
        "agent": "opencode",
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": worktree,
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan",
    }

    with pytest.raises(CoordinatorError) as error:
        phase("demo", data, 1)

    assert error.value.code == "invalid_phase_run"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_dangling_phase_run_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    state = store.read()
    state["phase_runs"].append(
        {
            "phase": "plan",
            "attempt": 1,
            "owner": "planner",
            "work_item_id": "missing",
            "worker_role": "planner",
            "model": "model",
            "reasoning": "high",
            "agent": "opencode",
            "session_id": "s",
            "process_id": "p",
            "command": "plan",
            "worktree": "/worktree",
            "expected_evidence": "plan",
            "observed_evidence": "plan",
            "next_action": "plan",
            "status": "completed",
            "question_status": "none",
        }
    )
    store.state_path.write_text(json.dumps(state))

    result = hermes_devlog("status", {"goal_id": "demo"})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_state"


def test_invalid_question_status_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    state = store.read()
    state["questions"].append(
        {
            "session_id": "s",
            "question": "which file?",
            "question_class": "general",
            "status": "invalid",
        }
    )
    store.state_path.write_text(json.dumps(state))

    result = hermes_devlog("status", {"goal_id": "demo"})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_state"


def test_integration_gate_accepts_json_evidence():
    assert (
        integration_gate(
            {"id": "gate", "status": "resolved", "evidence": ["verified"]}
        )["status"]
        == "resolved"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state.update(schema_version=99),
        lambda state: state.update(revision=0),
        lambda state: state.update(phase="bad"),
        lambda state: state.update(next_action=""),
        lambda state: state.update(capacity=0),
        lambda state: state.update(policy={}),
        lambda state: state.update(capacity=2),
        lambda state: state["goal_graph"].update(nodes={}),
        lambda state: state["goal_graph"]["nodes"]["demo"].pop("policy"),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(title=1),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(disposition="bad"),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(policy={}),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(repositories=[1]),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(source_bindings={}),
        lambda state: state["goal_graph"]["nodes"]["demo"].update(contract=[]),
        lambda state: state["goal_graph"].update(dependencies={}),
        lambda state: state["goal_graph"]["dependencies"].append(
            {"blocker": 1, "blocked": "demo"}
        ),
        lambda state: state["goal_graph"]["dependencies"].append(
            {"blocker": "missing", "blocked": "demo"}
        ),
        lambda state: state.update(work_items=[]),
        lambda state: state["work_items"]["demo"].update(phase="bad"),
        lambda state: state["work_items"]["demo"].update(next_action=""),
        lambda state: state["work_items"].update(bad=[]),
        lambda state: state.update(phase_runs={}),
        lambda state: state.update(reviews={}),
        lambda state: state.update(questions={}),
    ],
)
def test_persisted_state_rejects_invalid_shapes(tmp_path, monkeypatch, mutate):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    state = activate(activation())["state"]
    invalid = copy.deepcopy(state)
    mutate(invalid)
    with pytest.raises(CoordinatorError):
        validate_state(invalid)


def test_state_validation_accepts_deep_containment_graph():
    count = 1100
    policy = {
        "capacity": 1,
        "notifications": True,
        "discovered_work": True,
        "auto_merge": False,
        "require_human_merge_approval": True,
    }
    permissions = {
        "claim": False,
        "implement": True,
        "commit": False,
        "push": False,
        "create_issue": False,
        "create_pr": False,
        "post_review": False,
        "merge": False,
    }
    profile = {"name": "fallback", "match": "fallback", "sources": []}
    nodes = {
        f"{index:04}": {
            "id": f"{index:04}",
            "title": "x",
            "objective": "x",
            "success_criteria": [
                {
                    "id": "SC-1",
                    "description": "x",
                    "verification": "x",
                }
            ],
            "approach": [],
            "parent_id": f"{index + 1:04}" if index < count - 1 else None,
            "profile": profile,
            "permissions": permissions,
            "disposition": "open",
            "policy": policy,
        }
        for index in range(count)
    }

    validate_state(
        {
            "schema_version": 2,
            "revision": 1,
            "phase": "issue",
            "next_action": "x",
            "goal_graph": {"nodes": nodes, "dependencies": []},
            "work_items": {
                key: {"phase": "issue", "next_action": "x"} for key in nodes
            },
            "phase_runs": [],
            "reviews": [],
            "questions": [],
            "discovered_work": [],
            "gates": {"integration": [], "final_verification": False},
            "capacity": 1,
            "policy": policy,
            "completion": {
                "ready": False,
                "terminal": False,
                "review_remediation_required": False,
                "review_boundary_required": False,
            },
        }
    )


@pytest.mark.parametrize("field", ["schema_version", "revision"])
def test_persisted_state_rejects_boolean_version_fields(tmp_path, monkeypatch, field):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state[field] = True
    path.write_text(json.dumps(state))

    with pytest.raises(CoordinatorError):
        status("demo")


@pytest.mark.parametrize(("field", "value"), [("merge", True), ("capacity", 2)])
def test_persisted_child_policy_cannot_broaden_parent(
    tmp_path, monkeypatch, field, value
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["goal_graph"]["nodes"]["child"]["policy"][field] = value
    path.write_text(json.dumps(state))

    with pytest.raises(CoordinatorError):
        status("demo")


def test_persisted_policy_rejects_boolean_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["goal_graph"]["nodes"]["demo"]["policy"]["capacity"] = True
    path.write_text(json.dumps(state))

    with pytest.raises(CoordinatorError) as error:
        status("demo")

    assert error.value.code == "invalid_state"


def test_persisted_child_profile_cannot_broaden(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["goal_graph"]["nodes"]["child"]["profile"] = {
        "name": "native",
        "match": "native",
        "sources": ["unapproved.md"],
    }
    path.write_text(json.dumps(state))

    with pytest.raises(CoordinatorError) as error:
        status("demo")

    assert error.value.code == "invalid_state"
