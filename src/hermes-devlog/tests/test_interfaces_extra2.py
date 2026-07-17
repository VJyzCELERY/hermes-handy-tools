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
