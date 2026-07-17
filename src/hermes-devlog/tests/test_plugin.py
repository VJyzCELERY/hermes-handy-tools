import json
from importlib.metadata import entry_points

import pytest

from hermes_devlog import plugin


class RecordingContext:
    def __init__(self):
        self.registration = None

    def register_tool(self, **kwargs):
        self.registration = kwargs


def test_package_exposes_hermes_plugin_entry_point():
    matches = [
        entry
        for entry in entry_points(group="hermes_agent.plugins")
        if entry.name == "hermes-devlog"
    ]

    assert len(matches) == 1
    assert matches[0].value == "hermes_devlog.plugin"


def test_plugin_registers_json_serializing_hermes_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = RecordingContext()

    plugin.register(context)

    assert context.registration is not None
    assert context.registration["name"] == "hermes_devlog"
    assert context.registration["toolset"] == "hermes-devlog"
    schema = context.registration["schema"]
    operations = schema["parameters"]["properties"]["operation"]["enum"]
    assert {
        "amend_config",
        "amend_state",
        "audit_list",
        "audit_show",
        "audit_validate",
        "audit_repair",
    } <= set(operations)

    result = context.registration["handler"](
        {"operation": "status", "payload": {"goal_id": "missing"}}
    )

    assert isinstance(result, str)
    assert json.loads(result) == {
        "ok": False,
        "error": {"code": "not_found", "message": "goal state does not exist"},
    }


@pytest.mark.parametrize("operation", ["status", "next"])
def test_plugin_handler_accepts_registry_kwargs(tmp_path, monkeypatch, operation):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = RecordingContext()
    plugin.register(context)

    result = context.registration["handler"](
        {"operation": operation, "payload": {"goal_id": "missing"}},
        task_id="test-task",
    )

    assert json.loads(result)["ok"] is False
