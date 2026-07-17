"""Review, question, scheduling, and completion operations."""

from collections.abc import Mapping

from .errors import CoordinatorError
from .service_common import (
    QUESTION_CLASSES,
    SENSITIVE_QUESTION_CLASSES,
    TERMINAL_DISPOSITIONS,
    _mutate,
    _store,
)
from .validation import (
    authority_reference,
    identifier,
    integration_gate,
    json_value,
    reject_secrets,
    review_identity,
)


def review(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record review evidence and invalidate prior bindings on drift."""
    if not isinstance(data, Mapping):
        raise CoordinatorError("invalid_object", "review data must be an object")
    reject_secrets(data)
    required = {"head", "base", "diff", "findings"}
    if set(data) != required or not all(
        isinstance(data[key], str) for key in required - {"findings"}
    ):
        raise CoordinatorError(
            "invalid_review", "review requires head, base, diff, and findings"
        )
    if not isinstance(data["findings"], list):
        raise CoordinatorError("invalid_review", "findings must be a list")
    for field in ("head", "base", "diff"):
        review_identity(data[field], f"review.{field}")

    def change(state):
        for prior in state["reviews"]:
            if prior["head"] != data["head"] or (
                prior["base"] == data["base"] and prior["diff"] != data["diff"]
            ):
                prior["valid"] = False
        state["reviews"].append(
            {
                **dict(data),
                "phase": state["phase"],
                "valid": not bool(data["findings"]),
            }
        )
        if data["findings"]:
            state["completion"]["review_remediation_required"] = True
        state["next_action"] = (
            "remediate_review" if data["findings"] else "continue_implementation"
        )
        return state

    return _mutate(goal_id, revision, "review", change)

def question(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record an answer or escalate a worker question."""
    if not isinstance(data, Mapping):
        raise CoordinatorError("invalid_object", "question data must be an object")
    reject_secrets(data)
    allowed = {
        "session_id",
        "question",
        "answer",
        "escalate",
        "reason",
        "question_class",
        "authority_reference",
    }
    if (
        set(data) - allowed
        or not isinstance(data.get("session_id"), str)
        or not data["session_id"]
        or not isinstance(data.get("question"), str)
        or not data["question"]
    ):
        raise CoordinatorError(
            "invalid_question", "session_id and question are required"
        )

    inferred_class = _question_class(data["question"])
    declared_class = data.get("question_class")
    if declared_class is not None and (
        not isinstance(declared_class, str) or declared_class not in QUESTION_CLASSES
    ):
        raise CoordinatorError("invalid_question", "unsupported question class")
    if "authority_reference" in data:
        authority_reference(data["authority_reference"])
    question_class = (
        inferred_class
        if inferred_class in SENSITIVE_QUESTION_CLASSES
        else declared_class or inferred_class
    )

    def change(state):
        matching_runs = [
            run
            for run in state["phase_runs"]
            if run["session_id"] == data["session_id"] and run["status"] == "running"
        ]
        if len(matching_runs) != 1:
            raise CoordinatorError(
                "invalid_session", "question session must have exactly one running run"
            )
        sensitive = (
            question_class in SENSITIVE_QUESTION_CLASSES
            or inferred_class in SENSITIVE_QUESTION_CLASSES
        )
        config = _store(goal_id).read_config()
        approved = (
            "authority_reference" in data
            and not sensitive
            and _authority_is_verified(data["authority_reference"], state, config)
        )
        escalated = (
            not approved
            or bool(data.get("escalate"))
            or not data.get("answer")
        )
        item = {
            **dict(data),
            "question_class": question_class,
            "status": "needs_user" if escalated else "answered",
        }
        if "authority_reference" in data and not approved:
            item["escalate"] = True
        state["questions"].append(item)
        for run in state["phase_runs"]:
            if run["session_id"] == data["session_id"] and run["status"] == "running":
                run["question_status"] = (
                    "needs_user"
                    if any(
                        question["session_id"] == data["session_id"]
                        and question["status"] == "needs_user"
                        for question in state["questions"]
                    )
                    else "answered"
                )
        state["next_action"] = (
            "needs_user"
            if any(
                question["session_id"] == data["session_id"]
                and question["status"] == "needs_user"
                for question in state["questions"]
            )
            else "resume_session"
        )
        return state

    return _mutate(goal_id, revision, "question", change)


def resolve_question(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record Hermes authority resolving a question waiting for the user."""
    if not isinstance(data, Mapping):
        raise CoordinatorError(
            "invalid_object", "question resolution must be an object"
        )
    reject_secrets(data)
    if (
        set(data) - {"session_id", "answer", "authority_reference"}
        or not isinstance(data.get("session_id"), str)
        or not data["session_id"]
        or not isinstance(data.get("answer"), str)
        or not data["answer"]
        or "authority_reference" not in data
    ):
        raise CoordinatorError(
            "invalid_question",
            "question resolution requires session_id, answer, and authority_reference",
        )
    authority_reference(data["authority_reference"])

    def change(state):
        config = _store(goal_id).read_config()
        matching_runs = [
            run
            for run in state["phase_runs"]
            if run["session_id"] == data["session_id"] and run["status"] == "running"
        ]
        if len(matching_runs) != 1:
            raise CoordinatorError(
                "invalid_session", "question session must have exactly one running run"
            )
        pending = next(
            (
                item
                for item in reversed(state["questions"])
                if item["session_id"] == data["session_id"]
                and item["status"] == "needs_user"
            ),
            None,
        )
        if pending is None:
            raise CoordinatorError(
                "question_unresolved", "question session has no pending question"
            )
        verified = _authority_is_verified(data["authority_reference"], state, config)
        pending.update(
            {
                "answer": data["answer"],
                "authority_reference": data["authority_reference"],
                "status": "answered" if verified else "needs_user",
            }
        )
        if verified:
            pending.pop("escalate", None)
        else:
            pending["escalate"] = True
        has_pending = any(
            item["session_id"] == data["session_id"]
            and item["status"] == "needs_user"
            for item in state["questions"]
        )
        matching_runs[0]["question_status"] = (
            "needs_user" if has_pending else "answered"
        )
        state["next_action"] = "needs_user" if has_pending else "resume_session"
        return state

    return _mutate(goal_id, revision, "resolve_question", change)


def _authority_is_verified(reference: str, state: Mapping, config: Mapping) -> bool:
    """Require an authority reference to resolve in pinned state or rules."""
    source, _, target = reference.partition(":")
    if source == "rules":
        return target in config["profile"]["sources"]
    current = state
    for part in target.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def status(goal_id: str) -> dict:
    """Return current state without mutation."""
    return {"state": _store(goal_id).read()}

def _question_class(text: str) -> str:
    """Classify questions conservatively before accepting worker answers."""
    lowered = text.lower()
    if any(word in lowered for word in ("merge", "authorize", "authorization")):
        return "merge"
    if any(word in lowered for word in ("password", "token", "credential", "secret")):
        return "credentials"
    if any(word in lowered for word in ("permission", "policy", "allowed", "allow")):
        return "policy"
    if any(word in lowered for word in ("approve", "approval", "human", "user")):
        return "external_approval"
    if "scope" in lowered:
        return "scope"
    return "general"

def _scheduled_action(state: Mapping) -> str:
    """Choose one ready child without mutating the graph."""
    if state.get("completion", {}).get("terminal"):
        return "merge_if_authorized"
    if any(
        item.get("disposition") == "open" for item in state.get("discovered_work", [])
    ):
        return "dispose_discovered_work"
    if state.get("gates", {}).get("integration"):
        return "resolve_integration_gates"
    runs = state.get("phase_runs", [])
    active = sum(
        run.get("status") == "running" for run in runs if isinstance(run, Mapping)
    )
    capacity = state.get("capacity", state.get("policy", {}).get("capacity", 1))
    if active >= capacity:
        return "wait_for_capacity"
    graph = state.get("goal_graph", {})
    nodes = graph.get("nodes", {})
    dependencies = graph.get("dependencies", [])
    blocked = {
        edge.get("blocked")
        for edge in dependencies
        if nodes.get(edge.get("blocker"), {}).get("disposition")
        not in TERMINAL_DISPOSITIONS
    }
    ready = sorted(
        node_id
        for node_id, node in nodes.items()
        if node.get("parent_id") is not None
        and node.get("disposition", "open") == "open"
        and node_id not in blocked
    )
    if ready:
        return (
            state.get("work_items", {})
            .get(ready[0], {})
            .get("next_action", f"begin_child:{ready[0]}")
        )
    return state.get("next_action", "begin_issue")

def next_action(goal_id: str) -> dict:
    """Return the deterministic resume action."""
    store = _store(goal_id)
    state = store.read()
    action = _scheduled_action(state)
    return {"next_action": action, "revision": state["revision"]}

def complete(goal_id: str, revision: int) -> dict:
    """Mark a goal merge-ready only after every completion gate passes."""
    store = _store(goal_id)
    config = store.read_config()

    def change(state):
        if state.get("phase") != "final_verification":
            raise CoordinatorError(
                "incomplete_workflow", "completion requires final verification"
            )
        if any(
            run.get("status") == "running"
            for run in state["phase_runs"]
            if isinstance(run, Mapping)
        ):
            raise CoordinatorError(
                "active_phase_run", "completion requires all phase runs to finish"
            )
        if any(
            run.get("question_status") == "needs_user"
            for run in state["phase_runs"]
            if isinstance(run, Mapping)
        ) or any(
            item.get("status") == "needs_user"
            for item in state["questions"]
            if isinstance(item, Mapping)
        ):
            raise CoordinatorError(
                "question_unresolved",
                "completion requires all questions to be resolved",
            )
        required_phases = {
            "plan",
            "implement",
            "implementation_review",
            "pr_delivery",
            "final_verification",
        }
        recorded_phases = {
            run["phase"]
            for run in state["phase_runs"]
            if run["work_item_id"] == goal_id and run["status"] == "completed"
        }
        if not required_phases <= recorded_phases:
            raise CoordinatorError(
                "incomplete_workflow", "required workflow phase evidence is missing"
            )
        if (
            any(item.get("disposition") == "open" for item in state["discovered_work"])
            or state["gates"]["integration"]
            or not state["gates"]["final_verification"]
        ):
            raise CoordinatorError(
                "incomplete_gates", "completion gates are not satisfied"
            )
        reviews = state["reviews"]
        current_head = reviews[-1]["head"] if reviews else None
        current_bindings = {}
        for item in reviews:
            if item["head"] == current_head and item.get("valid"):
                current_bindings[(item["base"], item["diff"])] = item
        if not current_bindings or any(
            item.get("findings") or item.get("phase") != "implementation_review"
            for item in current_bindings.values()
        ):
            raise CoordinatorError(
                "stale_review", "stale review evidence cannot complete a goal"
            )
        if any(
            state["completion"].get(field)
            for field in ("review_remediation_required", "review_boundary_required")
        ):
            raise CoordinatorError(
                "incomplete_workflow",
                "review findings require remediation and a new implementation review",
            )
        nodes = state["goal_graph"]["nodes"]
        root_id = next(
            (
                node_id
                for node_id, node in nodes.items()
                if node.get("parent_id") is None
            ),
            None,
        )
        if root_id is None or any(
            node.get("disposition") not in TERMINAL_DISPOSITIONS
            or (
                node.get("disposition") == "resolved"
                and not required_phases <= {
                    run["phase"]
                    for run in state["phase_runs"]
                    if run["work_item_id"] == node_id
                    and run["status"] == "completed"
                }
            )
            for node_id, node in nodes.items()
            if node_id != root_id
        ):
            raise CoordinatorError(
                "incomplete_children",
                "resolved contained goals need terminal workflow evidence",
            )
        if any(
            nodes[edge["blocker"]].get("disposition") not in TERMINAL_DISPOSITIONS
            for edge in state["goal_graph"]["dependencies"]
        ):
            raise CoordinatorError(
                "incomplete_dependencies", "dependency blockers are unresolved"
            )
        if (
            not config["permissions"].get("merge", False)
            or not config["policy"].get("merge", False)
            or not state["policy"].get("merge", False)
        ):
            raise CoordinatorError(
                "merge_not_authorized", "merge permission and policy are required"
            )
        state["completion"] = {
            "ready": True,
            "terminal": True,
            "review_remediation_required": False,
            "review_boundary_required": False,
        }
        state["phase"] = "merge_ready"
        state["next_action"] = "merge_if_authorized"
        return state

    return {"state": store.mutate(revision, "complete", change)}

def gate(goal_id: str, name: str, value: object, revision: int) -> dict:
    """Record a verified integration or final-verification gate."""
    reject_secrets(value)
    if name not in {"final_verification", "integration"}:
        raise CoordinatorError("invalid_gate", "unsupported completion gate")
    if name == "final_verification":
        if not isinstance(value, bool):
            raise CoordinatorError("invalid_gate", "final verification must be boolean")
        integration = None
    else:
        integration = None if value is True else integration_gate(value)

    def change(state):
        if (
            name == "final_verification"
            and value
            and state.get("phase") != "final_verification"
        ):
            raise CoordinatorError(
                "invalid_gate",
                "final verification is only valid in final verification phase",
            )
        if name == "integration":
            if value is True:
                state["gates"][name] = []
            elif integration["status"] == "resolved":
                state["gates"][name] = [
                    item
                    for item in state["gates"][name]
                    if item["id"] != integration["id"]
                ]
            else:
                state["gates"][name] = [
                    item
                    for item in state["gates"][name]
                    if item["id"] != integration["id"]
                ] + [integration]
        else:
            state["gates"][name] = value
        return state

    return _mutate(goal_id, revision, "gate", change)

def discovered_work(goal_id: str, item: Mapping, revision: int) -> dict:
    """Record discovered work until Hermes explicitly disposes of it."""
    if not isinstance(item, Mapping):
        raise CoordinatorError("invalid_object", "discovered work must be an object")
    reject_secrets(item)
    if set(item) - {"id", "title", "disposition", "outcome"} or not item.get("id"):
        raise CoordinatorError("invalid_discovered_work", "discovered work needs an id")
    identifier(item["id"], "discovered_work.id")
    if "title" in item and not isinstance(item["title"], str):
        raise CoordinatorError(
            "invalid_discovered_work", "discovered work title must be a string"
        )
    if "outcome" in item:
        json_value(item["outcome"], "discovered_work.outcome")
    disposition = item.get("disposition", "open")
    if disposition not in {"open", "resolved", "deferred", "excluded"}:
        raise CoordinatorError("invalid_discovered_work", "unsupported disposition")

    def change(state):
        state["discovered_work"] = [
            old for old in state["discovered_work"] if old["id"] != item["id"]
        ]
        state["discovered_work"].append(
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "disposition": disposition,
                "outcome": item.get("outcome"),
            }
        )
        return state

    return _mutate(goal_id, revision, "discovered_work", change)
