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


@pytest.mark.parametrize(
    "worker_role,session_id", [("planner", "s"), ("reviewer", "s")]
)
def test_plan_review_requires_isolated_reviewer(
    tmp_path, monkeypatch, worker_role, session_id
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
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
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "plan-review",
    }
    phase("demo", phase_data, 1)

    with pytest.raises(CoordinatorError) as error:
        phase(
            "demo",
            {
                **phase_data,
                "phase": "plan_review",
                "attempt": 2,
                "worker_role": worker_role,
                "session_id": session_id,
            },
            2,
        )

    assert error.value.code == "invalid_phase_run"


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
    phase_data.update(
        {
            "phase": "plan_review",
            "attempt": 2,
            "worker_role": "reviewer",
            "session_id": "plan-review-session",
            "process_id": "plan-review-process",
        }
    )
    phase("demo", phase_data, 2)
    phase_data.update({"phase": "implement", "attempt": 3})
    phase_data["next_action"] = "implementation_review"
    phase("demo", phase_data, 3)
    phase_data.update(
        {
            "phase": "implementation_review",
            "attempt": 4,
            "worker_role": "reviewer",
            "session_id": "review-session",
            "process_id": "review-process",
        }
    )
    phase_data["next_action"] = "verify"
    phase_data["status"] = "running"
    phase("demo", phase_data, 4)
    question(
        "demo",
        {
            "session_id": "review-session",
            "question": "which file?",
            "answer": "service.py",
            "authority_reference": "state:policy",
        },
        5,
    )
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
    add_dependency("demo", "child", "demo", 2)

    from hermes_devlog.store import StateStore

    path = StateStore.from_goal("demo").state_path
    state = json.loads(path.read_text())
    state["goal_graph"]["dependencies"].append({"blocker": "demo", "blocked": "child"})
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

def test_declared_scope_question_requires_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    running_phase()

    result = question(
        "demo",
        {
            "session_id": "s",
            "question": "May I update the implementation?",
            "question_class": "scope",
            "answer": "yes",
            "authority_reference": "state:policy",
        },
        2,
    )

    item = result["state"]["questions"][-1]
    assert item["question_class"] == "scope"
    assert item["status"] == "needs_user"

def test_malformed_activity_record_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(activation())
    from hermes_devlog.store import StateStore

    StateStore.from_goal("demo").activity_path.write_text('{"revision": 2}\n')

    result = hermes_devlog("status", {"goal_id": "demo"})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_state"


def test_activation_recovers_if_state_replacement_is_interrupted(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from hermes_devlog.store import StateStore

    original = StateStore._atomic_json

    def interrupt_state_write(self, path, value):
        if path == self.state_path:
            raise KeyboardInterrupt
        original(self, path, value)

    monkeypatch.setattr(StateStore, "_atomic_json", interrupt_state_write)
    with pytest.raises(KeyboardInterrupt):
        activate(activation())

    monkeypatch.setattr(StateStore, "_atomic_json", original)
    assert status("demo")["state"]["revision"] == 1
