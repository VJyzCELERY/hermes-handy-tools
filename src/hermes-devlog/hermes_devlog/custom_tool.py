"""Thin custom-tool adapter delegating to the CLI service."""

from . import service
from .errors import CoordinatorError


def hermes_devlog(operation: str, payload: dict) -> dict:
    """Execute a supported declarative operation without external actions."""
    handlers = {
        "activate": lambda: service.activate(payload),
        "status": lambda: service.status(payload["goal_id"]),
        "next": lambda: service.next_action(payload["goal_id"]),
        "goal": lambda: service.add_goal(
            payload["goal_id"], payload["node"], payload["expected_revision"]
        ),
        "dependency": lambda: service.add_dependency(
            payload["goal_id"],
            payload["blocker"],
            payload["blocked"],
            payload["expected_revision"],
        ),
        "phase": lambda: service.phase(
            payload["goal_id"], payload["data"], payload["expected_revision"]
        ),
        "review": lambda: service.review(
            payload["goal_id"], payload["data"], payload["expected_revision"]
        ),
        "question": lambda: service.question(
            payload["goal_id"], payload["data"], payload["expected_revision"]
        ),
        "complete": lambda: service.complete(
            payload["goal_id"], payload["expected_revision"]
        ),
        "gate": lambda: service.gate(
            payload["goal_id"],
            payload["name"],
            payload["value"],
            payload["expected_revision"],
        ),
        "discovered_work": lambda: service.discovered_work(
            payload["goal_id"], payload["item"], payload["expected_revision"]
        ),
    }
    try:
        return {"ok": True, **handlers[operation]()}
    except CoordinatorError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except KeyError as exc:
        raise ValueError(f"unsupported operation: {operation}") from exc
