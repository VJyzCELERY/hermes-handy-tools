"""Pure coordinator operations backed by the local store."""

from collections.abc import Mapping
from copy import deepcopy

from .errors import CoordinatorError
from .store import StateStore
from .validation import (
    activation_payload,
    expected_revision,
    identifier,
    json_value,
    normalized_policy,
    reject_secrets,
)

TERMINAL_DISPOSITIONS = {"resolved", "deferred", "excluded"}
QUESTION_CLASSES = {
    "general",
    "scope",
    "credentials",
    "policy",
    "external_approval",
    "merge",
}


def _store(goal_id: str) -> StateStore:
    return StateStore.from_goal(goal_id)


def activate(payload: Mapping) -> dict:
    """Create a pinned goal and its initial resumable checkpoint."""
    data = activation_payload(payload)
    goal_id = data["goal_id"]
    policy = data.get("policy", {})
    config = {
        "schema_version": 1,
        "goal_id": goal_id,
        "title": data["title"],
        "template": deepcopy(data["template"]),
        "profile": deepcopy(data["profile"]),
        "route": deepcopy(data["route"]),
        "permissions": deepcopy(data["permissions"]),
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
                    "disposition": "open",
                    "policy": normalized_policy(policy),
                }
            },
            "dependencies": [],
        },
        "work_items": {},
        "phase_runs": [],
        "reviews": [],
        "questions": [],
        "discovered_work": [],
        "gates": {"integration": [], "final_verification": False},
        "capacity": config["policy"]["capacity"],
        "policy": deepcopy(config["policy"]),
        "completion": {"ready": False, "terminal": False},
    }
    return {"state": _store(goal_id).create(config, state)}


def _mutate(goal_id: str, revision: int, operation: str, change) -> dict:
    return {"state": _store(goal_id).mutate(revision, operation, change)}


def add_goal(goal_id: str, node: Mapping, revision: int) -> dict:
    """Add a recursively contained goal node."""
    reject_secrets(node)
    data = dict(node)
    if set(data) - {
        "id",
        "title",
        "parent_id",
        "repositories",
        "contract",
        "policy",
        "disposition",
    }:
        raise CoordinatorError("unknown_field", "unknown goal field")
    child_id = identifier(data.get("id"), "goal.id")
    if not isinstance(data.get("title"), str) or not data["title"]:
        raise CoordinatorError("invalid_title", "goal title must be non-empty")
    if data.get("disposition", "open") not in {
        "open",
        *TERMINAL_DISPOSITIONS,
    }:
        raise CoordinatorError("invalid_goal", "unsupported goal disposition")

    def change(state):
        nodes = state["goal_graph"]["nodes"]
        if child_id in nodes:
            raise CoordinatorError("duplicate_goal", "goal already exists")
        parent_id = data.get("parent_id", goal_id)
        if parent_id not in nodes:
            raise CoordinatorError("missing_parent", "parent goal does not exist")
        child_policy = data.get("policy", {})
        parent = nodes[parent_id]
        parent_policy = dict(state.get("policy", {}))
        parent_policy.update(parent.get("policy", {}))
        normalized_child_policy = normalized_policy(child_policy)
        child_policy = {
            field: normalized_child_policy[field] for field in child_policy
        }
        for field, child_value in child_policy.items():
            parent_value = parent_policy.get(field, normalized_policy({})[field])
            if field == "capacity" and child_value > parent_value:
                raise CoordinatorError(
                    "policy_broadening", "child capacity cannot exceed parent capacity"
                )
            if field != "capacity" and child_value and not parent_value:
                raise CoordinatorError(
                    "policy_broadening",
                    f"child {field} policy cannot broaden parent authority",
                )
        node_copy = deepcopy(data)
        node_copy["id"] = child_id
        node_copy["parent_id"] = parent_id
        node_copy.setdefault("disposition", "open")
        effective_policy = dict(parent_policy)
        effective_policy.update(child_policy)
        node_copy["policy"] = effective_policy
        nodes[child_id] = node_copy
        return state

    return _mutate(goal_id, revision, "add_goal", change)


def add_dependency(goal_id: str, blocker: str, blocked: str, revision: int) -> dict:
    """Add a dependency edge while preserving DAG semantics."""
    identifier(blocker, "blocker")
    identifier(blocked, "blocked")

    def change(state):
        nodes = state["goal_graph"]["nodes"]
        if blocker not in nodes or blocked not in nodes:
            raise CoordinatorError("missing_goal", "dependency endpoint does not exist")
        edge = {"blocker": blocker, "blocked": blocked}
        edges = state["goal_graph"]["dependencies"]
        if edge in edges:
            raise CoordinatorError("duplicate_dependency", "dependency already exists")
        graph = {node: [] for node in nodes}
        for existing in [*edges, edge]:
            graph[existing["blocker"]].append(existing["blocked"])
        visiting, visited = set(), set()

        def walk(node):
            if node in visiting:
                raise CoordinatorError(
                    "dependency_cycle", "dependency graph must be acyclic"
                )
            if node in visited:
                return
            visiting.add(node)
            for child in graph[node]:
                walk(child)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            walk(node)
        edges.append(edge)
        return state

    return _mutate(goal_id, revision, "add_dependency", change)


def phase(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record a worker phase with explicit ownership and checkpoint."""
    expected_revision(revision)
    reject_secrets(data)
    allowed = {
        "phase",
        "attempt",
        "owner",
        "session_id",
        "process_id",
        "command",
        "worktree",
        "expected_evidence",
        "observed_evidence",
        "next_action",
        "status",
    }
    if set(data) - allowed:
        raise CoordinatorError("unknown_field", "unknown phase field")
    if not data.get("owner"):
        raise CoordinatorError("missing_owner", "phase ownership is required")
    required = {
        "phase",
        "attempt",
        "owner",
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
    phases = [
        "issue",
        "plan",
        "implement",
        "implementation_review",
        "remediation",
        "merge_ready",
    ]
    if data.get("phase") not in phases:
        raise CoordinatorError("invalid_transition", "unsupported workflow phase")

    def change(state):
        current = state["phase"]
        target = data["phase"]
        allowed_targets = {
            "issue": {"issue", "plan"},
            "plan": {"plan", "implement"},
            "implement": {"implement", "implementation_review", "remediation"},
            "implementation_review": {
                "implementation_review",
                "remediation",
                "merge_ready",
            },
            "remediation": {"remediation", "implement", "implementation_review"},
            "merge_ready": {"merge_ready"},
        }
        if target not in allowed_targets[current]:
            raise CoordinatorError(
                "invalid_transition", f"cannot move from {current} to {target}"
            )
        if target == "merge_ready" and not state["completion"].get("ready"):
            raise CoordinatorError(
                "incomplete_gates", "merge-ready requires completed gates"
            )
        if current == "merge_ready" and target != current:
            raise CoordinatorError(
                "invalid_transition", "terminal workflow phase cannot move"
            )
        state["phase"] = target
        state["next_action"] = data.get("next_action", f"continue_{target}")
        state["phase_runs"].append(dict(data))
        return state

    return _mutate(goal_id, revision, "phase", change)


def review(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record review evidence and invalidate prior bindings on drift."""
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

    def change(state):
        for prior in state["reviews"]:
            if any(prior[key] != data[key] for key in ("head", "base", "diff")):
                prior["valid"] = False
        state["reviews"].append({**dict(data), "valid": not bool(data["findings"])})
        state["next_action"] = (
            "remediate_review" if data["findings"] else "continue_implementation"
        )
        return state

    return _mutate(goal_id, revision, "review", change)


def question(goal_id: str, data: Mapping, revision: int) -> dict:
    """Record an answer or escalate a worker question."""
    reject_secrets(data)
    allowed = {
        "session_id",
        "question",
        "answer",
        "escalate",
        "reason",
        "question_class",
    }
    if set(data) - allowed or not data.get("session_id") or not data.get("question"):
        raise CoordinatorError(
            "invalid_question", "session_id and question are required"
        )

    question_class = data.get("question_class") or _question_class(data["question"])
    if not isinstance(question_class, str) or question_class not in QUESTION_CLASSES:
        raise CoordinatorError("invalid_question", "unsupported question class")

    def change(state):
        sensitive = question_class in {
            "credentials",
            "policy",
            "external_approval",
            "merge",
        }
        escalated = sensitive or bool(data.get("escalate")) or not data.get("answer")
        item = {
            **dict(data),
            "question_class": question_class,
            "status": "needs_user" if escalated else "answered",
        }
        state["questions"].append(item)
        state["next_action"] = "needs_user" if escalated else "resume_session"
        return state

    return _mutate(goal_id, revision, "question", change)


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
    if state.get("discovered_work"):
        return "dispose_discovered_work"
    if state.get("gates", {}).get("integration"):
        return "resolve_integration_gates"
    runs = state.get("phase_runs", [])
    active = sum(
        run.get("status") in {"running", "active", "in_progress"}
        for run in runs
        if isinstance(run, Mapping)
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
        return f"begin_child:{ready[0]}"
    return state.get("next_action", "begin_issue")


def next_action(goal_id: str) -> dict:
    """Return the deterministic resume action."""
    store = _store(goal_id)
    state = store.read()
    action = _scheduled_action(state)
    if action != state["next_action"] and hasattr(store, "set_next_action"):
        state = store.set_next_action(action)
    return {"next_action": action, "revision": state["revision"]}


def complete(goal_id: str, revision: int) -> dict:
    """Mark a goal merge-ready only after every completion gate passes."""
    store = _store(goal_id)
    config = store.read_config()

    def change(state):
        if state.get("phase") not in {"implementation_review", "remediation"}:
            raise CoordinatorError(
                "incomplete_workflow", "completion requires implementation review"
            )
        if (
            state["discovered_work"]
            or state["gates"]["integration"]
            or not state["gates"]["final_verification"]
        ):
            raise CoordinatorError(
                "incomplete_gates", "completion gates are not satisfied"
            )
        reviews = state["reviews"]
        current_review = reviews[-1] if reviews else None
        if (
            current_review is None
            or not current_review.get("valid")
            or current_review.get("findings")
        ):
            raise CoordinatorError(
                "stale_review", "stale review evidence cannot complete a goal"
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
            for node_id, node in nodes.items()
            if node_id != root_id
        ):
            raise CoordinatorError(
                "incomplete_children", "all contained goals must be terminal"
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
        state["completion"] = {"ready": True, "terminal": True}
        state["phase"] = "merge_ready"
        state["next_action"] = "merge_if_authorized"
        return state

    return {"state": store.mutate(revision, "complete", change)}


def gate(goal_id: str, name: str, value: object, revision: int) -> dict:
    """Record a verified integration or final-verification gate."""
    if name not in {"final_verification", "integration"}:
        raise CoordinatorError("invalid_gate", "unsupported completion gate")

    def change(state):
        if name == "integration":
            state["gates"][name] = [] if value is True else [value]
        else:
            if not isinstance(value, bool):
                raise CoordinatorError(
                    "invalid_gate", "final verification must be boolean"
                )
            state["gates"][name] = value
        return state

    return _mutate(goal_id, revision, "gate", change)


def discovered_work(goal_id: str, item: Mapping, revision: int) -> dict:
    """Record discovered work until Hermes explicitly disposes of it."""
    if set(item) - {"id", "title", "disposition"} or not item.get("id"):
        raise CoordinatorError("invalid_discovered_work", "discovered work needs an id")
    disposition = item.get("disposition", "open")
    if disposition not in {"open", "resolved", "deferred", "excluded"}:
        raise CoordinatorError("invalid_discovered_work", "unsupported disposition")

    def change(state):
        state["discovered_work"] = [
            old for old in state["discovered_work"] if old["id"] != item["id"]
        ]
        if disposition == "open":
            state["discovered_work"].append(
                {
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "disposition": "open",
                }
            )
        return state

    return _mutate(goal_id, revision, "discovered_work", change)
