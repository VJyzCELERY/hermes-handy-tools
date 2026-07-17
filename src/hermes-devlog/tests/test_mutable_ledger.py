"""Public behavior for the amendable, auditable ledger."""

import copy
import json

import pytest

from hermes_devlog.errors import CoordinatorError
from hermes_devlog.service import (
    activate,
    amend_config,
    amend_state,
    audit_list,
    audit_repair,
    audit_show,
    audit_validate,
    phase,
)
from hermes_devlog.store import StateStore


def _payload() -> dict:
    return {
        "goal_id": "demo-goal",
        "title": "Demo goal",
        "template": {
            "release": "v1.0.0",
            "commit": "a" * 40,
            "manifest_hash": "b" * 64,
            "snapshot": "snapshots/demo",
        },
        "profile": {"name": "native", "match": "native", "sources": []},
        "routes": {
            role: {"model": "old-model", "reasoning": "high", "agent": "opencode"}
            for role in ("planner", "reviewer", "worker")
        },
        "permissions": {"implement": True, "merge": False},
        "repositories": ["org/demo"],
        "source_bindings": {"issue": "#1"},
        "completion_contract": {"final_verification": True},
    }


def _phase() -> dict:
    return {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "demo-goal",
        "worker_role": "planner",
        "model": "old-model",
        "reasoning": "high",
        "agent": "opencode",
        "session_id": "session",
        "process_id": "process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "plan",
        "next_action": "implement",
    }


def test_amendments_are_revision_checked_validated_and_accept_safe_extra(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())

    config = amend_config(
        "demo-goal",
        {"extra": {"tracking": [1, {"label": "safe"}]}},
        reason="add tracking metadata",
        expected_revision=1,
    )
    state = amend_state(
        "demo-goal",
        {"next_action": "resume", "extra": {}},
        reason="correct resume action",
        expected_revision=2,
    )

    assert config["config"]["extra"] == {"tracking": [1, {"label": "safe"}]}
    assert state["state"]["next_action"] == "resume"
    with pytest.raises(CoordinatorError, match="revision"):
        amend_config("demo-goal", {"extra": {}}, reason="stale", expected_revision=1)
    with pytest.raises(CoordinatorError, match="secret"):
        amend_state(
            "demo-goal",
            {"extra": {"token": "no"}},
            reason="invalid",
            expected_revision=3,
        )
    assert StateStore.from_goal("demo-goal").read()["revision"] == 3


def test_route_amendment_preserves_completed_phase_route_snapshot(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())
    phase("demo-goal", _phase(), 1)
    routes = copy.deepcopy(_payload()["routes"])
    routes["planner"]["model"] = "new-model"

    amended = amend_config(
        "demo-goal", {"routes": routes}, reason="change planner", expected_revision=2
    )

    old_run = amended["state"]["phase_runs"][0]
    assert old_run["route"] == {
        "model": "old-model",
        "reasoning": "high",
        "agent": "opencode",
    }
    assert amended["config"]["routes"]["planner"]["model"] == "new-model"


def test_hash_linked_audit_lists_shows_validates_and_repairs_state(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())
    amend_state(
        "demo-goal", {"next_action": "resume"}, reason="resume", expected_revision=1
    )
    store = StateStore.from_goal("demo-goal")

    events = audit_list("demo-goal", limit=1)["events"]
    assert [event["revision"] for event in events] == [2]
    assert audit_show("demo-goal", 1)["event"]["previous_hash"] is None
    assert audit_validate("demo-goal")["valid"] is True

    store.state_path.write_text(json.dumps({"broken": True}))
    with pytest.raises(CoordinatorError, match="state"):
        audit_validate("demo-goal")
    repaired = audit_repair(
        "demo-goal", reason="restore audited state", expected_revision=2
    )
    assert repaired["state"]["next_action"] == "resume"
    assert audit_validate("demo-goal")["valid"] is True
