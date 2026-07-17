"""JSON command-line interface for the local coordinator."""

import json
import sys

from . import service
from .errors import CoordinatorError
from .validation import strict_mapping

OPERATIONS = {
    "activate",
    "amend_config",
    "amend_state",
    "audit_list",
    "audit_show",
    "audit_validate",
    "audit_repair",
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
}


def _dispatch(operation: str, payload: dict) -> dict:
    if operation not in OPERATIONS:
        raise CoordinatorError(
            "unsupported_operation", f"unsupported operation: {operation}"
        )
    envelopes = {
        "activate": {
            "goal_id",
            "title",
            "template",
            "profile",
            "routes",
            "permissions",
            "policy",
            "repositories",
            "source_bindings",
            "completion_contract",
            "contract",
        },
        "status": {"goal_id"},
        "next": {"goal_id"},
        "amend_config": {
            "goal_id",
            "patch",
            "reason",
            "audit_extra",
            "expected_revision",
        },
        "amend_state": {
            "goal_id",
            "patch",
            "reason",
            "audit_extra",
            "expected_revision",
        },
        "audit_list": {"goal_id", "limit"},
        "audit_show": {"goal_id", "revision"},
        "audit_validate": {"goal_id"},
        "audit_repair": {"goal_id", "reason", "audit_extra", "expected_revision"},
        "goal": {"goal_id", "node", "expected_revision"},
        "goal_disposition": {
            "goal_id",
            "child_id",
            "disposition",
            "expected_revision",
        },
        "dependency": {
            "goal_id",
            "blocker",
            "blocked",
            "extra",
            "expected_revision",
        },
        "phase": {"goal_id", "data", "expected_revision"},
        "review": {"goal_id", "data", "expected_revision"},
        "question": {"goal_id", "data", "expected_revision"},
        "resolve_question": {"goal_id", "data", "expected_revision"},
        "complete": {"goal_id", "expected_revision"},
        "gate": {"goal_id", "name", "value", "expected_revision"},
        "discovered_work": {"goal_id", "item", "expected_revision"},
    }
    payload = strict_mapping(payload, envelopes[operation], f"{operation} envelope")
    if operation == "activate":
        return service.activate(payload)
    goal_id = payload["goal_id"]
    if operation == "status":
        return service.status(goal_id)
    if operation == "next":
        return service.next_action(goal_id)
    if operation == "audit_list":
        return service.audit_list(goal_id, payload.get("limit", 20))
    if operation == "audit_show":
        return service.audit_show(goal_id, payload["revision"])
    if operation == "audit_validate":
        return service.audit_validate(goal_id)
    revision = payload["expected_revision"]
    if operation == "amend_config":
        return service.amend_config(
            goal_id,
            payload["patch"],
            reason=payload["reason"],
            expected_revision=revision,
            audit_extra=payload.get("audit_extra"),
        )
    if operation == "amend_state":
        return service.amend_state(
            goal_id,
            payload["patch"],
            reason=payload["reason"],
            expected_revision=revision,
            audit_extra=payload.get("audit_extra"),
        )
    if operation == "audit_repair":
        return service.audit_repair(
            goal_id,
            reason=payload["reason"],
            expected_revision=revision,
            audit_extra=payload.get("audit_extra"),
        )
    if operation == "goal":
        return service.add_goal(goal_id, payload["node"], revision)
    if operation == "goal_disposition":
        return service.set_goal_disposition(
            goal_id, payload["child_id"], payload["disposition"], revision
        )
    if operation == "dependency":
        return service.add_dependency(
            goal_id,
            payload["blocker"],
            payload["blocked"],
            revision,
            payload.get("extra"),
        )
    if operation in {"phase", "review", "question", "resolve_question"}:
        return getattr(service, operation)(goal_id, payload["data"], revision)
    if operation == "complete":
        return service.complete(goal_id, revision)
    if operation == "gate":
        return service.gate(goal_id, payload["name"], payload["value"], revision)
    if operation == "discovered_work":
        return service.discovered_work(goal_id, payload["item"], revision)
    raise AssertionError("supported operation was not dispatched")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process status."""
    args = list(argv if argv is not None else sys.argv[1:])
    try:
        if len(args) != 2:
            raise CoordinatorError("usage", "usage: hermes-devlog OPERATION JSON")
        result = {"ok": True, **_dispatch(args[0], json.loads(args[1]))}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CoordinatorError, KeyError, TypeError, json.JSONDecodeError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, CoordinatorError)
            else {"code": "invalid_input", "message": str(exc)}
        )
        print(
            json.dumps({"ok": False, "error": error}, sort_keys=True), file=sys.stderr
        )
        return 1
