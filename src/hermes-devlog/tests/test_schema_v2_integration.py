"""End-to-end schema-v2 integration through the registered Hermes tool."""

import json

from hermes_devlog import plugin
from hermes_devlog.store import StateStore


class RecordingContext:
    """Minimal Hermes plugin registry surface for integration coverage."""

    registration: dict

    def register_tool(self, **kwargs) -> None:
        self.registration = kwargs


def _payload() -> dict:
    return {
        "goal_id": "schema-v2-goal",
        "title": "Schema v2 integration goal",
        "goal": {
            "objective": "Prove semantic goals and governed authority work end to end.",
            "success_criteria": [
                {
                    "id": "SC-1",
                    "description": "The plugin accepts and audits schema-v2 state.",
                    "verification": "plugin integration test",
                }
            ],
            "approach": ["activate", "amend", "validate"],
        },
        "governance": {
            "sources": [
                {
                    "id": "repo-rules",
                    "kind": "repository_rule",
                    "reference": "AGENTS.md",
                    "content_hash": "sha256:" + "c" * 64,
                    "snapshot_ref": "snapshots/governance/AGENTS.md",
                    "required": True,
                }
            ],
            "constraints": [
                {
                    "id": "human-merge",
                    "kind": "requirement",
                    "statement": "A human must approve any merge.",
                    "applies_to": ["merge"],
                    "enforcement": "human_gate",
                    "controls": [
                        "permissions.merge",
                        "policy.require_human_merge_approval",
                    ],
                    "overridable": False,
                }
            ],
        },
        "template": {
            "release": "v2",
            "commit": "a" * 40,
            "manifest_hash": "b" * 64,
            "snapshot": "snapshots/schema-v2",
        },
        "profile": {"name": "native", "match": "native", "sources": ["AGENTS.md"]},
        "routes": {
            role: {"model": "model", "reasoning": "high", "agent": "opencode"}
            for role in ("planner", "reviewer", "worker")
        },
        "permissions": {
            "claim": True,
            "implement": True,
            "commit": True,
            "push": True,
            "create_issue": False,
            "create_pr": True,
            "post_review": True,
            "merge": False,
        },
        "policy": {
            "capacity": 1,
            "notifications": True,
            "discovered_work": True,
            "auto_merge": False,
            "require_human_merge_approval": True,
        },
        "repositories": ["org/demo"],
        "source_bindings": {"issue": "#1"},
        "completion_contract": {"final_verification": True},
        "extra": {"integration": {"schema": 2}},
    }


def test_plugin_schema_v2_lifecycle_is_audited_and_authority_bound(
    tmp_path, monkeypatch
):
    """Exercise config, state, governance, child goal, and audit through plugin."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = RecordingContext()
    plugin.register(context)
    handler = context.registration["handler"]

    def call(operation: str, payload: dict) -> dict:
        result = json.loads(handler({"operation": operation, "payload": payload}))
        assert result["ok"], result
        return result

    activated = call("activate", _payload())
    assert activated["state"]["schema_version"] == 2
    assert (
        activated["state"]["goal_graph"]["nodes"]["schema-v2-goal"]["objective"]
        == _payload()["goal"]["objective"]
    )

    amended = call(
        "amend_config",
        {
            "goal_id": "schema-v2-goal",
            "expected_revision": 1,
            "reason": "Record a second governance constraint.",
            "patch": {
                "governance": {
                    **_payload()["governance"],
                    "constraints": [
                        *_payload()["governance"]["constraints"],
                        {
                            "id": "protect-sdk",
                            "kind": "prohibition",
                            "statement": "Do not modify the protected SDK.",
                            "applies_to": ["implement"],
                            "enforcement": "blocker",
                            "controls": ["permissions.implement"],
                            "overridable": False,
                        },
                    ],
                }
            },
        },
    )
    assert len(amended["config"]["governance"]["constraints"]) == 2

    child = call(
        "goal",
        {
            "goal_id": "schema-v2-goal",
            "expected_revision": 2,
            "node": {
                "id": "child-goal",
                "title": "Child semantic goal",
                "objective": "Validate child narrowing.",
                "success_criteria": [
                    {
                        "id": "SC-CHILD-1",
                        "description": "Child cannot broaden merge authority.",
                        "verification": "state validation",
                    }
                ],
                "permissions": {"merge": False},
                "policy": {"capacity": 1},
            },
        },
    )
    assert child["state"]["goal_graph"]["nodes"]["child-goal"]["objective"]

    audit = call("audit_list", {"goal_id": "schema-v2-goal", "limit": 3})
    assert [event["revision"] for event in audit["events"]] == [3, 2, 1]
    assert all(
        "config" not in event and "state" not in event for event in audit["events"]
    )
    assert call("audit_validate", {"goal_id": "schema-v2-goal"})["valid"] is True


def test_plugin_replays_route_changes_and_repairs_corrupt_materialized_state(
    tmp_path, monkeypatch
):
    """Exercise the full mutable-ledger recovery path through the plugin handler."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = RecordingContext()
    plugin.register(context)
    handler = context.registration["handler"]
    payload = _payload()
    payload["goal_id"] = "plugin-repair-goal"

    def call(operation: str, payload: dict) -> dict:
        result = json.loads(handler({"operation": operation, "payload": payload}))
        assert result["ok"], result
        return result

    call("activate", payload)
    plan_data = {
        "phase": "plan",
        "owner": "planner",
        "attempt": 1,
        "work_item_id": "plugin-repair-goal",
        "worker_role": "planner",
        "model": "model",
        "reasoning": "high",
        "agent": "opencode",
        "session_id": "plan-session",
        "process_id": "plan-process",
        "command": "plan",
        "worktree": "/plugin-repair-worktree",
        "expected_evidence": {"plan": "expected"},
        "observed_evidence": {"plan": "initial"},
        "next_action": "implement",
    }
    call(
        "phase",
        {
            "goal_id": "plugin-repair-goal",
            "expected_revision": 1,
            "data": plan_data,
        },
    )
    route_patch = {
        **payload["routes"],
        "worker": {"model": "model", "reasoning": "high", "agent": "claude-code"},
    }
    call(
        "amend_config",
        {
            "goal_id": "plugin-repair-goal",
            "expected_revision": 2,
            "patch": {"routes": route_patch},
            "reason": "Change worker route after planning.",
        },
    )
    implement_data = {
        **plan_data,
        "phase": "implement",
        "attempt": 2,
        "owner": "worker",
        "worker_role": "worker",
        "agent": "claude-code",
        "session_id": "implement-session",
        "process_id": "implement-process",
        "command": "implement",
        "observed_evidence": {"implementation": "initial"},
        "next_action": "review",
    }
    implemented = call(
        "phase",
        {
            "goal_id": "plugin-repair-goal",
            "expected_revision": 3,
            "data": implement_data,
        },
    )
    assert [run["route"]["agent"] for run in implemented["state"]["phase_runs"]] == [
        "opencode",
        "claude-code",
    ]
    corrected = call(
        "amend_state",
        {
            "goal_id": "plugin-repair-goal",
            "expected_revision": 4,
            "reason": "Correct plan evidence.",
            "patch": {
                "phase_runs": [
                    {
                        "session_id": "plan-session",
                        "attempt": 1,
                        "work_item_id": "plugin-repair-goal",
                        "observed_evidence": {"plan": "corrected"},
                    }
                ]
            },
        },
    )
    assert corrected["state"]["phase_runs"][0]["observed_evidence"] == {
        "plan": "corrected"
    }
    store = StateStore.from_goal("plugin-repair-goal")
    store.state_path.write_text('{"corrupt": true}')
    repaired = call(
        "audit_repair",
        {
            "goal_id": "plugin-repair-goal",
            "expected_revision": 5,
            "reason": "Restore the intentionally corrupted materialized state.",
        },
    )
    assert repaired["state"]["revision"] == 6
    assert call("audit_validate", {"goal_id": "plugin-repair-goal"})["valid"] is True
