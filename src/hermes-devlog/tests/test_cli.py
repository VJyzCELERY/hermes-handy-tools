import json

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
        "route": {"model": "openai/gpt-5.6-luna", "variant": "high"},
        "permissions": {"claim": True, "implement": True, "merge": False},
    }

    assert main(["activate", json.dumps(payload)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["state"]["revision"] == 1
    assert result["state"]["next_action"] == "begin_issue"
    assert (tmp_path / "dev-log" / "demo-goal" / "config.json").exists()
