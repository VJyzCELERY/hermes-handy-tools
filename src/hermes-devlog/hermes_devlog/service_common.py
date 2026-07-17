"""Shared coordinator service helpers."""

from .store import StateStore

TERMINAL_DISPOSITIONS = {"resolved", "deferred", "excluded"}
QUESTION_CLASSES = {
    "general",
    "scope",
    "credentials",
    "policy",
    "external_approval",
    "merge",
}
SENSITIVE_QUESTION_CLASSES = {
    "scope",
    "credentials",
    "policy",
    "external_approval",
    "merge",
}


def _store(goal_id: str) -> StateStore:
    return StateStore.from_goal(goal_id)


def _mutate(goal_id: str, revision: int, operation: str, change) -> dict:
    return {"state": _store(goal_id).mutate(revision, operation, change)}
