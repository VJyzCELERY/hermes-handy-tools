import json

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
    reject_secrets,
)


def activation(goal_id="demo"):
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
        "permissions": {"implement": True, "merge": False},
    }


def test_cli_and_custom_tool_have_equivalent_activation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    payload = activation("cli-goal")
    assert main(["activate", json.dumps(payload)]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "other"))
    tool_result = hermes_devlog("activate", activation("tool-goal"))
    assert cli_result["ok"] is True
    assert tool_result["ok"] is True
    assert tool_result["state"]["phase"] == cli_result["state"]["phase"]


def test_question_completion_and_discovered_work_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan-record",
        "observed_evidence": "plan-record",
        "next_action": "implement",
    }
    phase("demo", phase_data, 1)
    phase_data["phase"] = "implement"
    phase_data["next_action"] = "implementation_review"
    phase("demo", phase_data, 2)
    phase_data["phase"] = "implementation_review"
    phase_data["next_action"] = "verify"
    phase("demo", phase_data, 3)
    question("demo", {"session_id": "s", "question": "scope?"}, 4)
    discovered_work("demo", {"id": "bug", "title": "Bug"}, 5)
    with pytest.raises(CoordinatorError) as error:
        complete("demo", 6)
    assert error.value.code == "incomplete_gates"
    discovered_work("demo", {"id": "bug", "title": "Bug", "disposition": "deferred"}, 6)
    gate("demo", "final_verification", True, 7)
    review("demo", {"head": "h", "base": "b", "diff": "d", "findings": []}, 8)
    result = complete("demo", 9)
    assert result["state"]["completion"]["terminal"] is True


def test_cli_reports_structured_input_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert main(["unknown", "{}"]) == 1
    result = json.loads(capsys.readouterr().err)
    assert result["ok"] is False
    assert result["error"]["code"] == "unsupported_operation"


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


def test_service_rejects_invalid_graphs_and_records_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    with pytest.raises(CoordinatorError):
        add_goal("demo", {"id": "child", "title": "Child", "parent_id": "missing"}, 1)
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    with pytest.raises(CoordinatorError):
        add_goal("demo", {"id": "child", "title": "Child"}, 2)
    add_dependency("demo", "demo", "child", 2)
    with pytest.raises(CoordinatorError):
        add_dependency("demo", "demo", "child", 3)
    phase_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "session_id": "s",
        "process_id": "p",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan-record",
        "observed_evidence": "plan-record",
        "next_action": "plan",
    }
    phase("demo", phase_data, 3)
    phase_data["phase"] = "implement"
    phase_data["next_action"] = "implement"
    phase("demo", phase_data, 4)
    with pytest.raises(CoordinatorError):
        phase("demo", {"phase": "issue", "owner": "builder"}, 5)
    review("demo", {"head": "h", "base": "b", "diff": "d", "findings": ["one"]}, 5)
    question(
        "demo",
        {"session_id": "s", "question": "which file?", "answer": "the package"},
        6,
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
                "value": True,
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


@pytest.mark.parametrize(
    "operation",
    ["goal", "dependency", "phase", "review", "question", "complete", "gate"],
)
def test_cli_and_custom_tool_return_equivalent_malformed_input(
    operation, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert main([operation, json.dumps({"goal_id": "demo"})]) == 1
    cli_result = json.loads(capsys.readouterr().err)
    tool_result = hermes_devlog(operation, {"goal_id": "demo"})
    assert tool_result == cli_result


def test_question_and_review_secret_inputs_leave_state_and_activity_unchanged(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()
    activity_before = store.activity_path.read_text()
    for operation, data in [
        ("question", {"session_id": "s", "question": "api_token?"}),
        (
            "review",
            {"head": "h", "base": "b", "diff": "d", "findings": [{"token": "x"}]},
        ),
    ]:
        with pytest.raises(CoordinatorError) as error:
            getattr(service, operation)("demo", data, 1)
        assert error.value.code in {"secret_field", "secret_value"}
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_activity_records_are_timestamped_attributed_and_verified(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    gate("demo", "final_verification", True, 1)
    from hermes_devlog.store import StateStore

    records = [
        json.loads(line)
        for line in StateStore.from_goal("demo").activity_path.read_text().splitlines()
    ]
    assert len(records) == 2
    assert all(
        set(record) == {"timestamp", "actor", "operation", "revision", "verified"}
        and record["actor"]
        and record["verified"] is True
        for record in records
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("goal_id", "bad goal", "invalid_identifier"),
        ("title", "", "invalid_title"),
        ("template", {}, "invalid_template"),
        ("profile", {"name": "x", "match": "wrong", "sources": []}, "invalid_profile"),
        ("route", {"model": "", "variant": "high"}, "invalid_route"),
        ("permissions", {"implement": "yes"}, "invalid_permissions"),
        ("policy", {"capacity": 0}, "invalid_policy"),
    ],
)
def test_activation_rejects_invalid_fields(field, value, code):
    data = activation()
    data[field] = value
    with pytest.raises(CoordinatorError) as error:
        activation_payload(data)
    assert error.value.code == code


def test_validation_rejects_secret_values_and_bad_revisions():
    with pytest.raises(CoordinatorError) as error:
        reject_secrets("contains a secret")
    assert error.value.code == "secret_value"
    with pytest.raises(CoordinatorError) as error:
        expected_revision(True)
    assert error.value.code == "invalid_revision"
