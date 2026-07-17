"""Worker phase coordinator operations."""

from collections.abc import Mapping

from .errors import CoordinatorError
from .service_common import (
    _mutate,
    _store,
)
from .validation import (
    PHASE_RUN_STATUSES,
    QUESTION_STATUSES,
    expected_revision,
    identifier,
    json_value,
    normalized_absolute_path,
    reject_secrets,
)


def phase(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record a worker phase with explicit ownership and checkpoint."""
    expected_revision(revision)
    if not isinstance(data, Mapping):
        raise CoordinatorError("invalid_object", "phase data must be an object")
    reject_secrets(data)
    allowed = {
        "phase",
        "attempt",
        "owner",
        "work_item_id",
        "worker_role",
        "model",
        "variant",
        "session_id",
        "process_id",
        "command",
        "worktree",
        "expected_evidence",
        "observed_evidence",
        "next_action",
        "status",
        "question_status",
    }
    if set(data) - allowed:
        raise CoordinatorError("unknown_field", "unknown phase field")
    if not data.get("owner"):
        raise CoordinatorError("missing_owner", "phase ownership is required")
    required = {
        "phase",
        "attempt",
        "owner",
        "work_item_id",
        "worker_role",
        "model",
        "variant",
        "session_id",
        "process_id",
        "command",
        "worktree",
        "expected_evidence",
        "observed_evidence",
        "next_action",
    }
    if not required <= set(data):
        raise CoordinatorError(
            "incomplete_phase_run", "phase run evidence is incomplete"
        )
    if (
        not isinstance(data["attempt"], int)
        or isinstance(data["attempt"], bool)
        or data["attempt"] < 1
    ):
        raise CoordinatorError(
            "invalid_phase_run", "phase attempt must be a positive integer"
        )
    for field in required - {
        "phase",
        "attempt",
        "expected_evidence",
        "observed_evidence",
    }:
        if not isinstance(data[field], str) or not data[field]:
            raise CoordinatorError(
                "invalid_phase_run", f"phase {field} must be non-empty"
            )
    json_value(data["expected_evidence"], "phase.expected_evidence")
    json_value(data["observed_evidence"], "phase.observed_evidence")
    identifier(data["work_item_id"], "phase.work_item_id")
    normalized_absolute_path(data["worktree"], "phase.worktree", "invalid_phase_run")
    phase_status = data.get("status", "completed")
    if not isinstance(phase_status, str) or phase_status not in PHASE_RUN_STATUSES:
        raise CoordinatorError("invalid_phase_run", "unsupported phase run status")
    question_status = data.get("question_status", "none")
    if not isinstance(question_status, str) or question_status not in QUESTION_STATUSES:
        raise CoordinatorError(
            "invalid_phase_run", "unsupported phase run question status"
        )
    phases = [
        "issue",
        "plan",
        "plan_review",
        "implement",
        "implementation_review",
        "remediation",
        "pr_delivery",
        "final_verification",
        "merge_ready",
    ]
    if data.get("phase") not in phases:
        raise CoordinatorError("invalid_transition", "unsupported workflow phase")

    def change(state):
        work_item = state["work_items"].get(data["work_item_id"])
        if work_item is None:
            raise CoordinatorError("missing_work_item", "work item does not exist")
        current = work_item["phase"]
        target = data["phase"]
        matching_runs = [
            run
            for run in state["phase_runs"]
            if run["session_id"] == data["session_id"]
            and run["attempt"] == data["attempt"]
        ]
        if len(matching_runs) > 1:
            raise CoordinatorError(
                "invalid_phase_run", "phase session and attempt are not unique"
            )
        matching_run = matching_runs[0] if matching_runs else None
        config = _store(goal_id).read_config()
        if (
            data["model"] != config["route"]["model"]
            or data["variant"] != config["route"]["variant"]
        ):
            raise CoordinatorError(
                "route_mismatch", "phase run does not use the pinned model route"
            )
        allowed_targets = {
            "issue": {"issue", "plan"},
            "plan": {"plan", "plan_review"},
            "plan_review": {"plan_review", "implement"},
            "implement": {"implement", "implementation_review", "remediation"},
            "implementation_review": {
                "implementation_review",
                "remediation",
                "pr_delivery",
            },
            "remediation": {"remediation", "implement", "implementation_review"},
            "pr_delivery": {"pr_delivery", "final_verification"},
            "final_verification": {"final_verification", "merge_ready"},
            "merge_ready": {"merge_ready"},
        }
        if target not in allowed_targets[current]:
            raise CoordinatorError(
                "invalid_transition", f"cannot move from {current} to {target}"
            )
        if target in {"implement", "remediation"} and not config["permissions"].get(
            "implement", False
        ):
            raise CoordinatorError(
                "implementation_not_authorized",
                "implementation permission is required",
            )
        if matching_run and matching_run.get("question_status") == "needs_user":
            raise CoordinatorError(
                "question_unresolved",
                "phase run is waiting for question resolution",
            )
        active = sum(
            run.get("status") == "running"
            for run in state["phase_runs"]
            if isinstance(run, Mapping) and run is not matching_run
        )
        if phase_status == "running" and active >= state["capacity"]:
            raise CoordinatorError(
                "capacity_exceeded", "active phase capacity has been reached"
            )
        if any(
            run.get("status") == "running"
            and run.get("work_item_id") == data["work_item_id"]
            and run is not matching_run
            for run in state["phase_runs"]
            if isinstance(run, Mapping)
        ):
            raise CoordinatorError(
                "active_phase_run", "work item has an active phase run"
            )
        if target == "merge_ready" and not state["completion"].get("ready"):
            raise CoordinatorError(
                "incomplete_gates", "merge-ready requires completed gates"
            )
        if current == "merge_ready" and target != current:
            raise CoordinatorError(
                "invalid_transition", "terminal workflow phase cannot move"
            )
        if target in {"implement", "remediation"}:
            state["gates"]["final_verification"] = False
            for item in state["reviews"]:
                item["valid"] = False
            if state["completion"]["review_remediation_required"]:
                state["completion"]["review_remediation_required"] = False
                state["completion"]["review_boundary_required"] = True
        elif target == "implementation_review":
            if state["completion"]["review_boundary_required"]:
                state["completion"]["review_boundary_required"] = False
        next_action = data.get("next_action", f"continue_{target}")
        work_item.update({"phase": target, "next_action": next_action})
        if data["work_item_id"] == goal_id:
            state["phase"] = target
            state["next_action"] = next_action
        run = {
            **dict(data),
            "status": phase_status,
            "question_status": question_status,
        }
        if matching_run is None:
            state["phase_runs"].append(run)
        else:
            matching_run.update(run)
        return state

    return _mutate(goal_id, revision, "phase", change)
