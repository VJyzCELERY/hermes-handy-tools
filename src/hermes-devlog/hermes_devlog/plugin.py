"""Hermes Agent plugin bridge for the development ledger."""

from __future__ import annotations

import json
from typing import Any

from .custom_tool import hermes_devlog as _run_operation

TOOL_SCHEMA = {
    "name": "hermes_devlog",
    "description": (
        "Record and inspect bounded Hermes workflow state in the local dev-log "
        "ledger. This tool records intent and evidence; Hermes still owns "
        "external actions such as GitHub, OpenCode, notifications, and merges."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "activate",
                    "status",
                    "next",
                    "goal",
                    "goal_disposition",
                    "dependency",
                    "phase",
                    "review",
                    "question",
                    "resolve_question",
                    "complete",
                    "gate",
                    "discovered_work",
                ],
                "description": "Declarative ledger operation to perform.",
            },
            "payload": {
                "type": "object",
                "description": "Operation-specific JSON object accepted by the ledger.",
            },
        },
        "required": ["operation", "payload"],
        "additionalProperties": False,
    },
}


def _handle(args: dict[str, Any], **_: Any) -> str:
    """Run the adapter and serialize its result for Hermes tool dispatch."""
    result = _run_operation(
        operation=args["operation"],
        payload=args["payload"],
    )
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def register(ctx: Any) -> None:
    """Register the development-log tool through Hermes's plugin context."""
    ctx.register_tool(
        name="hermes_devlog",
        toolset="hermes-devlog",
        schema=TOOL_SCHEMA,
        handler=_handle,
        description=TOOL_SCHEMA["description"],
        emoji="📒",
    )
