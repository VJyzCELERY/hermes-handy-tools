import json
from pathlib import Path

from hermes_devlog.cli import main


def test_activation_persists_pinned_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    payload = {
        "goal_id": "demo-goal",
        "title": "Demo goal",
        "template": {
            "release": "v1.0.0",
            "commit": "a" * 40,
            "manifest_hash": "b" * 64,
            "snapshot": "snapshots/demo",
        },
        "profile": {"name": "native", "match": "native", "sources": ["AGENTS.md"]},
        "routes": {
            "planner": {
                "model": "openai/gpt-5.6-luna", "reasoning": "high", "agent": "opencode"
            },
            "reviewer": {
                "model": "openai/gpt-5.6-terra",
                "reasoning": "high",
                "agent": "opencode",
            },
            "worker": {
                "model": "openai/gpt-5.6-luna", "reasoning": "high", "agent": "opencode"
            },
        },
        "permissions": {"claim": True, "implement": True, "merge": False},
        "repositories": ["org/demo"],
        "source_bindings": {"issue": "#1", "spec": "#4"},
        "completion_contract": {"final_verification": True},
    }

    assert main(["activate", json.dumps(payload)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["state"]["revision"] == 1
    assert result["state"]["next_action"] == "begin_issue"
    assert (tmp_path / "dev-log" / "demo-goal" / "config.json").exists()
    amendment = {
        "goal_id": "demo-goal",
        "patch": {"extra": {}},
        "reason": "add metadata",
        "expected_revision": 1,
    }
    assert main(["amend_state", json.dumps(amendment)]) == 0
    assert main(["audit_validate", json.dumps({"goal_id": "demo-goal"})]) == 0


def test_replacement_skill_is_between_three_and_five_kilobytes():
    skill = Path(__file__).parents[1] / "skills" / "hermes-development-log.md"
    assert 3072 <= skill.stat().st_size <= 5120
