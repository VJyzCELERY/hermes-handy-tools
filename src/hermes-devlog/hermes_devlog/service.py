"""Pure coordinator operations backed by the local store."""

from collections.abc import Mapping
from copy import deepcopy

from .errors import CoordinatorError
from .goal_service import add_dependency, add_goal, set_goal_disposition
from .phase_service import phase
from .service_common import _store
from .validation import (
    activation_payload,
    extra_metadata,
    normalized_policy,
    reject_secrets,
)
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
    "amend_config",
    "amend_state",
    "audit_list",
    "audit_repair",
    "audit_show",
    "audit_validate",
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
        "permissions": deepcopy(data["permissions"]),
        "repositories": deepcopy(data["repositories"]),
        "source_bindings": deepcopy(data["source_bindings"]),
        contract_field: deepcopy(data[contract_field]),
        "policy": normalized_policy(policy),
        "extra": deepcopy(data.get("extra", {})),
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
        "extra": {},
    }
    return {"state": _store(goal_id).create(config, state)}


def amend_config(
    goal_id: str,
    patch: Mapping,
    *,
    reason: str | None = None,
    expected_revision: int,
    audit_extra: Mapping | None = None,
) -> dict:
    """Apply a validated partial config replacement at one revision."""
    if not isinstance(patch, Mapping):
        raise CoordinatorError("invalid_object", "config patch must be an object")
    forbidden = {"schema_version", "goal_id"} & set(patch)
    if forbidden:
        raise CoordinatorError("immutable_field", "config identity cannot be amended")
    reject_secrets(patch)

    def change(config: dict) -> dict:
        config.update(deepcopy(dict(patch)))
        if "extra" in config:
            config["extra"] = extra_metadata(config["extra"], "config.extra")
        return config

    audit_metadata = extra_metadata(audit_extra or {}, "audit.extra")
    config, state = _store(goal_id).amend_config(
        expected_revision, change, reason, dict(patch), audit_metadata
    )
    return {"config": config, "state": state}


def amend_state(
    goal_id: str,
    patch: Mapping,
    *,
    reason: str | None = None,
    expected_revision: int,
    audit_extra: Mapping | None = None,
) -> dict:
    """Apply a validated partial state replacement at one revision."""
    if not isinstance(patch, Mapping):
        raise CoordinatorError("invalid_object", "state patch must be an object")
    forbidden = {"schema_version", "revision"} & set(patch)
    if forbidden:
        raise CoordinatorError("immutable_field", "state revision cannot be amended")
    reject_secrets(patch)

    def change(state: dict) -> dict:
        patch_copy = deepcopy(dict(patch))
        if "phase_runs" in patch_copy:
            _correct_phase_runs(state["phase_runs"], patch_copy.pop("phase_runs"))
        state.update(patch_copy)
        state["extra"] = extra_metadata(state["extra"], "state.extra")
        return state

    return {
        "state": _store(goal_id).amend_state(
            expected_revision,
            change,
            reason,
            dict(patch),
            extra_metadata(audit_extra or {}, "audit.extra"),
        )
    }


def audit_list(goal_id: str, limit: int = 20) -> dict:
    """List bounded latest-first immutable audit events."""
    return {"events": _store(goal_id).audit_list(limit)}


def audit_show(goal_id: str, revision: int) -> dict:
    """Show one immutable audit event."""
    return {"event": _store(goal_id).audit_show(revision)}


def audit_validate(goal_id: str) -> dict:
    """Validate audit linkage and current materialized files."""
    return _store(goal_id).audit_validate()


def audit_repair(
    goal_id: str,
    *,
    reason: str | None = None,
    expected_revision: int,
    audit_extra: Mapping | None = None,
) -> dict:
    """Repair materialized config and state from the audited head."""
    config, state = _store(goal_id).audit_repair(
        expected_revision, reason, extra_metadata(audit_extra or {}, "audit.extra")
    )
    return {"config": config, "state": state}


def _correct_phase_runs(current: list[dict], correction: object) -> None:
    """Merge evidence corrections while preserving each recorded route snapshot."""
    if not isinstance(correction, list):
        raise CoordinatorError(
            "invalid_phase_run", "phase run correction must be a list"
        )
    indexed = {
        (run["session_id"], run["attempt"], run["work_item_id"]): run
        for run in current
    }
    for patch in correction:
        if not isinstance(patch, Mapping):
            raise CoordinatorError(
                "invalid_phase_run", "phase run correction is invalid"
            )
        identity = (
            patch.get("session_id"),
            patch.get("attempt"),
            patch.get("work_item_id"),
        )
        run = indexed.get(identity)
        if run is None:
            raise CoordinatorError(
                "invalid_phase_run", "phase run correction is missing"
            )
        route = deepcopy(run["route"])
        run.update(deepcopy(dict(patch)))
        if run.get("route", route) != route:
            raise CoordinatorError(
                "immutable_field", "phase route snapshot cannot change"
            )
        run["route"] = route
