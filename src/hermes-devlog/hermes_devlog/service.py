"""Pure coordinator operations backed by the local store."""

from collections.abc import Mapping
from copy import deepcopy

from .goal_service import add_dependency, add_goal, set_goal_disposition
from .phase_service import phase
from .service_common import _store
from .validation import activation_payload, normalized_policy
from .workflow_service import (
    complete,
    discovered_work,
    gate,
    next_action,
    question,
    resolve_question,
    review,
    status,
)

__all__ = [
    "activate",
    "add_dependency",
    "add_goal",
    "complete",
    "discovered_work",
    "gate",
    "next_action",
    "phase",
    "question",
    "resolve_question",
    "review",
    "set_goal_disposition",
    "status",
]


def activate(payload: Mapping) -> dict:
    """Create a pinned goal and its initial resumable checkpoint."""
    data = activation_payload(payload)
    goal_id = data["goal_id"]
    contract_field = (
        "completion_contract" if "completion_contract" in data else "contract"
    )
    policy = data.get("policy", {})
    config = {
        "schema_version": 1,
        "goal_id": goal_id,
        "title": data["title"],
        "template": deepcopy(data["template"]),
        "profile": deepcopy(data["profile"]),
        "routes": deepcopy(data["routes"]),
        "harness": data["harness"],
        "permissions": deepcopy(data["permissions"]),
        "repositories": deepcopy(data["repositories"]),
        "source_bindings": deepcopy(data["source_bindings"]),
        contract_field: deepcopy(data[contract_field]),
        "policy": normalized_policy(policy),
    }
    state = {
        "schema_version": 1,
        "revision": 1,
        "phase": "issue",
        "next_action": "begin_issue",
        "goal_graph": {
            "nodes": {
                goal_id: {
                    "id": goal_id,
                    "title": data["title"],
                    "parent_id": None,
                    "profile": deepcopy(data["profile"]),
                    "permissions": deepcopy(data["permissions"]),
                    "repositories": deepcopy(data["repositories"]),
                    "source_bindings": deepcopy(data["source_bindings"]),
                    contract_field: deepcopy(data[contract_field]),
                    "disposition": "open",
                    "policy": normalized_policy(policy),
                }
            },
            "dependencies": [],
        },
        "work_items": {goal_id: {"phase": "issue", "next_action": "begin_issue"}},
        "phase_runs": [],
        "reviews": [],
        "questions": [],
        "discovered_work": [],
        "gates": {"integration": [], "final_verification": False},
        "capacity": config["policy"]["capacity"],
        "policy": deepcopy(config["policy"]),
        "completion": {
            "ready": False,
            "terminal": False,
            "review_remediation_required": False,
            "review_boundary_required": False,
        },
    }
    return {"state": _store(goal_id).create(config, state)}
