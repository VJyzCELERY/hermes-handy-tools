"""Approved mutable-ledger contract regressions."""

import json
from copy import deepcopy

import pytest

from hermes_devlog.errors import CoordinatorError
from hermes_devlog.service import (
    activate,
    amend_state,
    audit_list,
    audit_repair,
    audit_show,
    audit_validate,
    phase,
    status,
)
from hermes_devlog.store import StateStore


def _payload() -> dict:
    return {
        "goal_id": "contract-goal",
        "title": "Contract goal",
        "template": {
            "release": "v1",
            "commit": "a" * 40,
            "manifest_hash": "b" * 64,
            "snapshot": "snapshots/contract",
        },
        "profile": {"name": "native", "match": "native", "sources": []},
        "routes": {
            role: {"model": "model", "reasoning": "high", "agent": "opencode"}
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
        "work_item_id": "contract-goal",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high",
        "agent": "opencode",
        "session_id": "session",
        "process_id": "process",
        "command": "plan",
        "worktree": "/worktree",
        "expected_evidence": "plan",
        "observed_evidence": "A",
        "next_action": "implement",
        "extra": {"source": "worker"},
    }


def test_contract_amendments_are_reasoned_replayable_and_compact(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())
    phase("contract-goal", _phase(), 1)

    with pytest.raises(CoordinatorError, match="reason"):
        amend_state("contract-goal", {"next_action": "resume"}, expected_revision=2)
    amended = amend_state(
        "contract-goal",
        {"phase_runs": [{**_phase(), "observed_evidence": "B"}]},
        reason="correct worker evidence",
        expected_revision=2,
    )
    event = audit_show("contract-goal", 3)["event"]
    summary = audit_list("contract-goal", limit=1)["events"][0]

    assert amended["state"]["phase_runs"][0]["observed_evidence"] == "B"
    assert amended["state"]["phase_runs"][0]["route"]["model"] == "model"
    assert {"target", "reason", "change", "before_digest", "after_digest"} <= set(event)
    assert event["reason"] == "correct worker evidence"
    assert "state" not in summary and "config" not in summary
    assert audit_validate("contract-goal")["valid"] is True

    store = StateStore.from_goal("contract-goal")
    store.state_path.write_text(json.dumps({"broken": True}))
    repaired = audit_repair(
        "contract-goal", reason="restore audited state", expected_revision=3
    )
    assert repaired["state"]["revision"] == 4
    assert audit_show("contract-goal", 4)["event"]["operation"] == "audit_repair"
    assert audit_validate("contract-goal")["valid"] is True


def test_state_amendment_cannot_broaden_root_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())
    current = status("contract-goal")["state"]
    graph = deepcopy(current["goal_graph"])
    graph["nodes"]["contract-goal"]["permissions"]["merge"] = True

    with pytest.raises(CoordinatorError, match="authority"):
        amend_state(
            "contract-goal",
            {"goal_graph": graph},
            reason="attempt to broaden authority",
            expected_revision=1,
        )

    assert status("contract-goal")["state"]["revision"] == 1


def test_bounded_audit_list_does_not_traverse_full_history(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    activate(_payload())
    store = StateStore.from_goal("contract-goal")
    store._read_audit = lambda: pytest.fail("audit list traversed history")

    events = store.audit_list(limit=1)

    assert len(events) == 1
    assert events[0]["revision"] == 1
