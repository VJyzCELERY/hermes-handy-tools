"""Pure coordinator operations backed by the local store."""

from collections.abc import Mapping
from copy import deepcopy

from .errors import CoordinatorError
from .store import StateStore
from .validation import (
    activation_payload,
    expected_revision,
    identifier,
    reject_secrets,
)

TERMINAL_DISPOSITIONS = {"resolved", "deferred", "excluded"}


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
        "policy": {"capacity": policy.get("capacity", 1), **policy},
    }
    state = {
        "schema_version": 1,
        "revision": 1,
        "phase": "issue",
        "next_action": "begin_issue",
        "goal_graph": {
            "nodes": {
                goal_id: {"id": goal_id, "title": data["title"], "parent_id": None}
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
        parent_policy = state.get("policy", {})
        if child_policy.get(
            "capacity", parent_policy.get("capacity", 1)
        ) > parent_policy.get("capacity", 1):
            raise CoordinatorError(
                "policy_broadening", "child capacity cannot exceed parent capacity"
            )
        node_copy = deepcopy(data)
        node_copy["id"] = child_id
        node_copy["parent_id"] = parent_id
        node_copy.setdefault("disposition", "open")
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
        state["phase_runs"].append(
            {"phase": target, "attempt": data.get("attempt", 1), **dict(data)}
        )
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
    allowed = {"session_id", "question", "answer", "escalate", "reason"}
    if set(data) - allowed or not data.get("session_id") or not data.get("question"):
        raise CoordinatorError(
            "invalid_question", "session_id and question are required"
        )

    def change(state):
        escalated = bool(data.get("escalate")) or not data.get("answer")
        item = {**dict(data), "status": "needs_user" if escalated else "answered"}
        state["questions"].append(item)
        state["next_action"] = "needs_user" if escalated else "resume_session"
        return state

    return _mutate(goal_id, revision, "question", change)


def status(goal_id: str) -> dict:
    """Return current state without mutation."""
    return {"state": _store(goal_id).read()}


def next_action(goal_id: str) -> dict:
    """Return the deterministic resume action."""
    state = _store(goal_id).read()
    return {"next_action": state["next_action"], "revision": state["revision"]}


def complete(goal_id: str, revision: int) -> dict:
    """Mark a goal merge-ready only after every completion gate passes."""

    def change(state):
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
        state["completion"] = {"ready": True, "terminal": True}
        state["phase"] = "merge_ready"
        state["next_action"] = "merge_if_authorized"
        return state

    return _mutate(goal_id, revision, "complete", change)


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
            state["discovered_work"].append(dict(item))
        return state

    return _mutate(goal_id, revision, "discovered_work", change)
