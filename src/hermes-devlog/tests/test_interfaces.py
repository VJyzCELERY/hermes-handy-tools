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
    activate(activation(merge=True))
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
        "next_action": "implement",
    }
    phase("demo", phase_data, 1)
    phase_data.update({"phase": "plan_review", "attempt": 2})
    phase("demo", phase_data, 2)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase_data["next_action"] = "implementation_review"
    phase("demo", phase_data, 3)
    phase_data.update({"phase": "implementation_review", "attempt": 4})
    phase_data["next_action"] = "verify"
    phase_data["status"] = "running"
    phase("demo", phase_data, 4)
    question("demo", {"session_id": "s", "question": "scope?"}, 5)
    phase_data["status"] = "completed"
    phase("demo", phase_data, 6)
    discovered_work("demo", {"id": "bug", "title": "Bug"}, 7)
    with pytest.raises(CoordinatorError) as error:
        complete("demo", 8)
    assert error.value.code == "incomplete_workflow"
    discovered_work(
        "demo",
        {
            "id": "bug",
            "title": "Bug",
            "disposition": "deferred",
            "outcome": "deferred to follow-up",
        },
        8,
    )
    review("demo", {"head": "h", "base": "b", "diff": "d", "findings": []}, 9)
    phase_data.update({"phase": "pr_delivery", "attempt": 5, "status": "completed"})
    phase("demo", phase_data, 10)
    phase_data.update({"phase": "final_verification", "attempt": 6})
    phase("demo", phase_data, 11)
    gate("demo", "final_verification", True, 12)
    result = complete("demo", 13)
    assert result["state"]["completion"]["terminal"] is True


def test_final_verification_false_is_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())

    result = gate("demo", "final_verification", False, 1)

    assert result["state"]["gates"]["final_verification"] is False
    assert result["state"]["revision"] == 2


def test_final_verification_gate_requires_current_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())

    with pytest.raises(CoordinatorError) as error:
        gate("demo", "final_verification", True, 1)

    assert error.value.code == "invalid_gate"


def test_boolean_capacity_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    invalid = activation()
    invalid["policy"] = {"capacity": True}

    with pytest.raises(CoordinatorError) as error:
        activate(invalid)
    assert error.value.code == "invalid_policy"

    state = activate(activation())["state"]
    state["capacity"] = True
    with pytest.raises(CoordinatorError) as error:
        validate_state(state)
    assert error.value.code == "invalid_state"


def test_question_class_cannot_bypass_sensitive_escalation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    running_phase()

    result = question(
        "demo",
        {
            "session_id": "s",
            "question": "May I merge this change?",
            "question_class": "general",
            "answer": "yes",
        },
        2,
    )

    item = result["state"]["questions"][-1]
    assert item["question_class"] == "merge"
    assert item["status"] == "needs_user"


def test_non_string_question_returns_structured_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    payload = {
        "goal_id": "demo",
        "data": {"session_id": "s", "question": 1},
        "expected_revision": 1,
    }

    assert main(["question", json.dumps(payload)]) == 1
    cli_result = json.loads(capsys.readouterr().err)
    tool_result = hermes_devlog("question", payload)

    assert cli_result == tool_result
    assert cli_result["error"]["code"] == "invalid_question"


def test_persisted_dependency_cycle_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    add_goal("demo", {"id": "child", "title": "Child"}, 1)
    add_dependency("demo", "demo", "child", 2)

    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["goal_graph"]["dependencies"].append({"blocker": "child", "blocked": "demo"})
    path.write_text(json.dumps(state))

    result = hermes_devlog("status", {"goal_id": "demo"})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_state"


def test_malformed_state_returns_structured_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    StateStore.from_goal("demo").state_path.write_text("{")

    assert main(["status", json.dumps({"goal_id": "demo"})]) == 1
    cli_result = json.loads(capsys.readouterr().err)
    tool_result = hermes_devlog("status", {"goal_id": "demo"})

    assert cli_result == tool_result
    assert cli_result["error"]["code"] == "invalid_state"


def test_root_goal_persists_repositories_and_source_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = activation()
    result = activate(data)
    root = result["state"]["goal_graph"]["nodes"]["demo"]

    assert root["repositories"] == data["repositories"]
    assert root["source_bindings"] == data["source_bindings"]
    assert root["completion_contract"] == data["completion_contract"]


def test_discovered_work_terminal_disposition_is_retained(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    discovered_work(
        "demo",
        {
            "id": "bug",
            "title": "Bug",
            "disposition": "excluded",
            "outcome": "outside agreed scope",
        },
        1,
    )

    item = status("demo")["state"]["discovered_work"][0]

    assert item == {
        "id": "bug",
        "title": "Bug",
        "disposition": "excluded",
        "outcome": "outside agreed scope",
    }


def test_cli_reports_structured_input_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert main(["unknown", "{}"]) == 1
    result = json.loads(capsys.readouterr().err)
    assert result["ok"] is False
    assert result["error"]["code"] == "unsupported_operation"


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
    add_dependency("demo", "demo", "child", 2)
    with pytest.raises(CoordinatorError):
        add_dependency("demo", "demo", "child", 3)
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
    gate("demo", "final_verification", False, 1)
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


def test_github_token_is_rejected_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    store = StateStore.from_goal("demo")
    before = store.read()
    activity_before = store.activity_path.read_text()

    with pytest.raises(CoordinatorError) as error:
        service.gate(
            "demo",
            "integration",
            {"id": "github", "status": "open", "evidence": "ghp_" + "a" * 36},
            1,
        )

    assert error.value.code == "secret_value"
    assert store.read() == before
    assert store.activity_path.read_text() == activity_before


def test_scope_questions_require_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    running_phase()

    result = question(
        "demo",
        {
            "session_id": "s",
            "question": "May I expand scope?",
            "question_class": "general",
            "answer": "yes",
        },
        2,
    )

    item = result["state"]["questions"][-1]
    assert item["question_class"] == "scope"
    assert item["status"] == "needs_user"


def test_unclassified_question_without_authority_reference_requires_user(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    running_phase()

    result = question(
        "demo",
        {
            "session_id": "s",
            "question": "Can I make this unrelated change?",
            "question_class": "general",
            "answer": "yes",
        },
        2,
    )

    assert result["state"]["questions"][-1]["status"] == "needs_user"


def test_activation_requires_profile_name(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = activation()
    del data["profile"]["name"]

    with pytest.raises(CoordinatorError) as error:
        activate(data)

    assert error.value.code == "invalid_profile"
    assert not (tmp_path / "dev-log" / "demo").exists()


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"extra": True}, "unknown_field"),
        ([], "invalid_object"),
    ],
)
def test_validation_rejects_invalid_mappings(value, code):
    with pytest.raises(CoordinatorError) as error:
        strict_mapping(value, {"known"}, "test")
    assert error.value.code == code


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
        "variant": "high",
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
            "variant": "high",
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
