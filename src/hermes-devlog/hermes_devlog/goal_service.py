"""Goal graph coordinator operations."""

from collections.abc import Mapping
from copy import deepcopy

from .errors import CoordinatorError
from .service_common import (
    TERMINAL_DISPOSITIONS,
    _mutate,
)
from .validation import (
    PROFILE_MATCH_RANK,
    extra_metadata,
    identifier,
    json_value,
    normalized_policy,
    permission_scope,
    profile_payload,
    reject_secrets,
)


def add_goal(goal_id: str, node: Mapping, revision: int) -> dict:
    """Add a recursively contained goal node."""
    data, child_id = _validated_goal(node)
    return _mutate(
        goal_id,
        revision,
        "add_goal",
        lambda state: _apply_goal(state, goal_id, data, child_id),
    )


def _validated_goal(node: Mapping) -> tuple[dict, str]:
    """Validate a child goal before acquiring the state lock."""
    if not isinstance(node, Mapping):
        raise CoordinatorError("invalid_object", "goal node must be an object")
    reject_secrets(node)
    data = dict(node)
    _validate_goal_fields(data)
    return data, identifier(data.get("id"), "goal.id")


def _validate_goal_fields(data: dict) -> None:
    """Validate the shape and evidence bindings of one child goal."""
    if set(data) - {
        "id",
        "title",
        "parent_id",
        "profile",
        "permissions",
        "repositories",
        "source_bindings",
        "completion_contract",
        "contract",
        "policy",
        "disposition",
    }:
        raise CoordinatorError("unknown_field", "unknown goal field")
    if not isinstance(data.get("title"), str) or not data["title"]:
        raise CoordinatorError("invalid_title", "goal title must be non-empty")
    if data.get("disposition", "open") not in {
        "open",
        *TERMINAL_DISPOSITIONS,
    }:
        raise CoordinatorError("invalid_goal", "unsupported goal disposition")
    if "permissions" in data:
        permission_scope(data["permissions"])
    _validate_goal_bindings(data)


def _validate_goal_bindings(data: dict) -> None:
    """Validate optional child-goal bindings."""
    if "repositories" in data and (
        not isinstance(data["repositories"], list)
        or not data["repositories"]
        or not all(isinstance(item, str) and item for item in data["repositories"])
    ):
        raise CoordinatorError("invalid_repositories", "goal repositories are invalid")
    if "source_bindings" in data:
        if (
            not isinstance(data["source_bindings"], (Mapping, list))
            or not data["source_bindings"]
        ):
            raise CoordinatorError(
                "invalid_binding", "source_bindings must be non-empty"
            )
        json_value(data["source_bindings"], "goal.source_bindings")
    if "profile" in data:
        profile_payload(data["profile"])
    contracts = [
        data[field] for field in ("completion_contract", "contract") if field in data
    ]
    if contracts and (
        len(contracts) != 1 or not isinstance(contracts[0], Mapping) or not contracts[0]
    ):
        raise CoordinatorError(
            "invalid_binding", "one non-empty completion contract is required"
        )
    if contracts:
        json_value(contracts[0], "goal.completion_contract")


def _apply_goal(state: dict, goal_id: str, data: dict, child_id: str) -> dict:
    """Apply one already validated child goal to state."""
    nodes = state["goal_graph"]["nodes"]
    if child_id in nodes:
        raise CoordinatorError("duplicate_goal", "goal already exists")
    parent_id = data.get("parent_id", goal_id)
    if parent_id not in nodes:
        raise CoordinatorError("missing_parent", "parent goal does not exist")
    parent = nodes[parent_id]
    parent_policy = dict(state.get("policy", {}))
    parent_policy.update(parent.get("policy", {}))
    parent_profile = parent["profile"]
    parent_permissions = parent["permissions"]
    if "repositories" in data and (
        "repositories" not in parent
        or not set(data["repositories"]).issubset(parent["repositories"])
    ):
        raise CoordinatorError(
            "scope_broadening", "child repositories must stay within parent scope"
        )
    child_profile = profile_payload(data.get("profile", parent_profile))
    if (
        PROFILE_MATCH_RANK[child_profile["match"]]
        < PROFILE_MATCH_RANK[parent_profile["match"]]
        or not set(child_profile["sources"]).issubset(parent_profile["sources"])
    ):
        raise CoordinatorError(
            "profile_broadening", "child profile cannot broaden parent profile"
        )
    child_policy = _narrow_policy(data.get("policy", {}), parent_policy)
    child_permissions = _narrow_permissions(
        data.get("permissions", {}), parent_permissions
    )
    node_copy = deepcopy(data)
    for field in ("repositories", "source_bindings"):
        if field not in node_copy and field in parent:
            node_copy[field] = deepcopy(parent[field])
    if "completion_contract" not in node_copy and "contract" not in node_copy:
        contract_field = next(
            field
            for field in ("completion_contract", "contract")
            if field in parent
        )
        node_copy[contract_field] = deepcopy(parent[contract_field])
    node_copy.update(
        {
            "id": child_id,
            "parent_id": parent_id,
            "disposition": data.get("disposition", "open"),
            "policy": {**parent_policy, **child_policy},
            "permissions": child_permissions,
            "profile": child_profile,
        }
    )
    nodes[child_id] = node_copy
    state["work_items"][child_id] = {
        "phase": "issue",
        "next_action": f"begin_child:{child_id}",
    }
    return state


def _narrow_permissions(child_permissions: object, parent_permissions: dict) -> dict:
    requested = (
        permission_scope(child_permissions) if child_permissions else {}
    )
    if set(requested) - set(parent_permissions):
        raise CoordinatorError(
            "permission_broadening", "child permissions must be inherited"
        )
    if any(
        value and not parent_permissions[permission]
        for permission, value in requested.items()
    ):
        raise CoordinatorError(
            "permission_broadening", "child permissions cannot broaden authority"
        )
    return {
        permission: allowed and requested.get(permission, True)
        for permission, allowed in parent_permissions.items()
    }


def _narrow_policy(child_policy: object, parent_policy: dict) -> dict:
    normalized = normalized_policy(child_policy)
    selected = {field: normalized[field] for field in child_policy}
    for field, child_value in selected.items():
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
    return selected

def set_goal_disposition(
    goal_id: str, child_id: str, disposition: str, revision: int
) -> dict:
    """Set a contained child goal's terminal disposition."""
    identifier(child_id, "goal_id")
    if disposition not in TERMINAL_DISPOSITIONS:
        raise CoordinatorError(
            "invalid_goal_disposition", "child disposition must be terminal"
        )

    def change(state):
        nodes = state["goal_graph"]["nodes"]
        node = nodes.get(child_id)
        if node is None:
            raise CoordinatorError("missing_goal", "goal does not exist")
        if node.get("parent_id") is None:
            raise CoordinatorError(
                "invalid_goal_disposition", "the root goal cannot be disposed"
            )
        if node.get("disposition") != "open":
            raise CoordinatorError(
                "invalid_goal_disposition", "only open child goals can be disposed"
            )
        node["disposition"] = disposition
        return state

    return _mutate(goal_id, revision, "goal_disposition", change)

def add_dependency(
    goal_id: str,
    blocker: str,
    blocked: str,
    revision: int,
    extra: Mapping | None = None,
) -> dict:
    """Add a dependency edge while preserving DAG semantics."""
    identifier(blocker, "blocker")
    identifier(blocked, "blocked")
    metadata = extra_metadata(extra or {}, "dependency.extra")

    def change(state):
        nodes = state["goal_graph"]["nodes"]
        if blocker not in nodes or blocked not in nodes:
            raise CoordinatorError("missing_goal", "dependency endpoint does not exist")
        if nodes[blocker].get("parent_id") is None:
            raise CoordinatorError(
                "invalid_dependency", "the root goal cannot block dependencies"
            )
        edge = {"blocker": blocker, "blocked": blocked, "extra": metadata}
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
