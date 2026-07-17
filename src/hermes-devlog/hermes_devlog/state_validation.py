"""Validation of persisted coordinator state."""

from collections.abc import Mapping

from .errors import CoordinatorError
from .validation import (
    PHASE_RUN_STATUSES,
    PHASES,
    POLICY_FIELDS,
    PROFILE_MATCH_RANK,
    QUESTION_RECORD_STATUSES,
    QUESTION_STATUSES,
    SENSITIVE_QUESTION_CLASSES,
    authority_reference,
    identifier,
    integration_gate,
    json_value,
    normalized_absolute_path,
    normalized_policy,
    permission_scope,
    profile_payload,
    review_identity,
    strict_mapping,
)


def _validate_goal_graph(graph: object, parent_policy: dict) -> dict:
    graph = strict_mapping(graph, {"nodes", "dependencies"}, "goal_graph")
    nodes = graph.get("nodes")
    if not isinstance(nodes, Mapping) or not nodes:
        raise CoordinatorError("invalid_state", "goal_graph.nodes must be non-empty")
    for node_id, node_value in nodes.items():
        _validate_goal_node(node_id, node_value)
    roots = [
        node_id for node_id, node in nodes.items() if node.get("parent_id") is None
    ]
    if len(roots) != 1:
        raise CoordinatorError("invalid_state", "goal graph must have exactly one root")
    _validate_policy_narrowing(nodes[roots[0]]["policy"], parent_policy)
    if any(
        node.get("parent_id") is not None and node.get("parent_id") not in nodes
        for node in nodes.values()
    ):
        raise CoordinatorError("invalid_state", "goal parent is missing")
    for node in nodes.values():
        parent_id = node.get("parent_id")
        if parent_id is not None:
            parent = nodes[parent_id]
            _validate_policy_narrowing(node["policy"], parent["policy"])
            if (
                PROFILE_MATCH_RANK[node["profile"]["match"]]
                < PROFILE_MATCH_RANK[parent["profile"]["match"]]
                or not set(node["profile"]["sources"]).issubset(
                    parent["profile"]["sources"]
                )
            ):
                raise CoordinatorError(
                    "invalid_state", "child profile broadens parent profile"
                )
            if "repositories" in node and (
                "repositories" not in parent
                or not set(node["repositories"]).issubset(parent["repositories"])
            ):
                raise CoordinatorError(
                    "invalid_state", "child repositories broaden parent scope"
                )
            parent_permissions = parent["permissions"]
            if set(node["permissions"]) != set(parent_permissions) or any(
                value and not parent_permissions[key]
                for key, value in node["permissions"].items()
            ):
                raise CoordinatorError(
                    "invalid_state", "child permissions broaden parent authority"
                )
    _validate_acyclic(
        {
            node_id: [node["parent_id"]] if node["parent_id"] else []
            for node_id, node in nodes.items()
        },
        "goal containment must be acyclic",
    )
    _validate_dependencies(graph.get("dependencies"), nodes)
    return nodes


def _validate_policy_narrowing(child: dict, parent: dict) -> None:
    if child["capacity"] > parent["capacity"] or any(
        child[field] and not parent[field] for field in POLICY_FIELDS - {"capacity"}
    ):
        raise CoordinatorError(
            "invalid_state", "child policy broadens parent authority"
        )


def _validate_goal_node(node_id: object, value: object) -> None:
    identifier(node_id, "goal_graph.nodes.key")
    node = strict_mapping(
        value,
        {
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
        },
        f"goal_graph.nodes.{node_id}",
    )
    if not {
        "id",
        "title",
        "parent_id",
        "profile",
        "permissions",
        "disposition",
        "policy",
    } <= set(node):
        raise CoordinatorError("invalid_state", "goal node schema is incomplete")
    if node.get("id") != node_id or not isinstance(node.get("title"), str):
        raise CoordinatorError(
            "invalid_state", "goal node identity or title is invalid"
        )
    if node.get("parent_id") is not None:
        identifier(node["parent_id"], "goal.parent_id")
    if node.get("disposition", "open") not in {
        "open",
        "resolved",
        "deferred",
        "excluded",
    }:
        raise CoordinatorError("invalid_state", "goal disposition is unsupported")
    _policy(node["policy"])
    permission_scope(node["permissions"])
    profile_payload(node["profile"])
    if "repositories" in node and (
        not isinstance(node["repositories"], list)
        or not node["repositories"]
        or not all(isinstance(item, str) and item for item in node["repositories"])
    ):
        raise CoordinatorError("invalid_state", "goal repositories are invalid")
    if "source_bindings" in node:
        if (
            not isinstance(node["source_bindings"], (Mapping, list))
            or not node["source_bindings"]
        ):
            raise CoordinatorError(
                "invalid_state", "goal source_bindings must be non-empty"
            )
        json_value(node["source_bindings"], "goal.source_bindings")
    contracts = [
        node[field] for field in ("completion_contract", "contract") if field in node
    ]
    if contracts and (
        len(contracts) != 1 or not isinstance(contracts[0], Mapping) or not contracts[0]
    ):
        raise CoordinatorError("invalid_state", "goal completion contract is invalid")
    if contracts:
        json_value(contracts[0], "goal.completion_contract")


def _policy(value: object) -> dict:
    data = strict_mapping(value, POLICY_FIELDS, "policy")
    if set(data) != POLICY_FIELDS:
        raise CoordinatorError("invalid_state", "goal policy is incomplete")
    if (
        not isinstance(data["capacity"], int)
        or isinstance(data["capacity"], bool)
        or data["capacity"] < 1
    ):
        raise CoordinatorError("invalid_state", "goal policy capacity is invalid")
    if any(
        not isinstance(data[field], bool) for field in POLICY_FIELDS - {"capacity"}
    ):
        raise CoordinatorError("invalid_state", "goal policy flags are invalid")
    return data


def _validate_acyclic(graph: dict, message: str) -> None:
    visited = set()
    visiting = set()
    for node_id in graph:
        if node_id in visited:
            continue
        stack = [(node_id, False)]
        while stack:
            current, exiting = stack.pop()
            if exiting:
                visiting.remove(current)
                visited.add(current)
                continue
            if current in visiting:
                raise CoordinatorError("invalid_state", message)
            if current in visited:
                continue
            visiting.add(current)
            stack.append((current, True))
            stack.extend((child_id, False) for child_id in graph[current])


def _validate_dependencies(value: object, nodes: Mapping) -> None:
    if not isinstance(value, list):
        raise CoordinatorError("invalid_state", "goal dependencies must be a list")
    graph = {node_id: [] for node_id in nodes}
    for edge in value:
        item = strict_mapping(edge, {"blocker", "blocked"}, "dependency")
        if not all(isinstance(item.get(key), str) for key in ("blocker", "blocked")):
            raise CoordinatorError(
                "invalid_state", "dependency endpoints must be strings"
            )
        if item["blocker"] not in nodes or item["blocked"] not in nodes:
            raise CoordinatorError("invalid_state", "dependency endpoint is missing")
        graph[item["blocker"]].append(item["blocked"])
    _validate_acyclic(graph, "dependency graph must be acyclic")


def _validate_work_items(value: object, nodes: Mapping) -> None:
    if not isinstance(value, Mapping) or set(value) != set(nodes):
        raise CoordinatorError(
            "invalid_state", "work_items must match goal graph nodes"
        )
    for key, item in value.items():
        identifier(key, "work_items.key")
        data = strict_mapping(item, {"phase", "next_action"}, f"work_items.{key}")
        if set(data) != {"phase", "next_action"} or data["phase"] not in PHASES:
            raise CoordinatorError("invalid_state", "work item checkpoint is invalid")
        if not isinstance(data["next_action"], str) or not data["next_action"]:
            raise CoordinatorError("invalid_state", "work item next_action is invalid")


def _validate_phase_runs(value: object, nodes: Mapping) -> None:
    fields = {
        "phase",
        "attempt",
        "owner",
        "work_item_id",
        "worker_role",
        "model",
        "reasoning",
        "agent",
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
    if not isinstance(value, list):
        raise CoordinatorError("invalid_state", "phase_runs must be a list")
    identities = set()
    session_attempts = {}
    for run in value:
        item = strict_mapping(run, fields, "phase_run")
        if set(item) != fields or item["phase"] not in PHASES:
            raise CoordinatorError("invalid_state", "phase run is incomplete")
        if (
            not isinstance(item["attempt"], int)
            or isinstance(item["attempt"], bool)
            or item["attempt"] < 1
        ):
            raise CoordinatorError("invalid_state", "phase run attempt is invalid")
        for field in fields - {
            "phase",
            "attempt",
            "expected_evidence",
            "observed_evidence",
        }:
            if not isinstance(item[field], str) or not item[field]:
                raise CoordinatorError("invalid_state", f"phase run {field} is invalid")
        identifier(item["work_item_id"], "phase_run.work_item_id")
        identity = (
            item["session_id"],
            item["attempt"],
            item["work_item_id"],
        )
        if identity in identities:
            raise CoordinatorError("invalid_state", "phase run identity is duplicated")
        identities.add(identity)
        session_attempt = (item["session_id"], item["attempt"])
        prior_work_item = session_attempts.setdefault(
            session_attempt, item["work_item_id"]
        )
        if prior_work_item != item["work_item_id"]:
            raise CoordinatorError(
                "invalid_state", "phase session and attempt cross work items"
            )
        identifier(item["worker_role"], "phase_run.worker_role")
        if item["work_item_id"] not in nodes:
            raise CoordinatorError("invalid_state", "phase run work item is missing")
        normalized_absolute_path(
            item["worktree"], "phase_run.worktree", "invalid_state"
        )
        json_value(item["expected_evidence"], "phase_run.expected_evidence")
        json_value(item["observed_evidence"], "phase_run.observed_evidence")
        if (
            item["status"] not in PHASE_RUN_STATUSES
            or item["question_status"] not in QUESTION_STATUSES
        ):
            raise CoordinatorError("invalid_state", "phase run status is invalid")


def _validate_reviews(value: object) -> None:
    fields = {"head", "base", "diff", "findings", "valid", "phase"}
    if not isinstance(value, list):
        raise CoordinatorError("invalid_state", "reviews must be a list")
    for review in value:
        item = strict_mapping(review, fields, "review")
        if set(item) != fields:
            raise CoordinatorError("invalid_state", "review binding is invalid")
        for field in ("head", "base", "diff"):
            review_identity(item[field], f"review.{field}")
        if not isinstance(item["findings"], list) or not isinstance(
            item["valid"], bool
        ):
            raise CoordinatorError("invalid_state", "review record is invalid")
        if item["phase"] not in PHASES:
            raise CoordinatorError("invalid_state", "review phase is unsupported")
        json_value(item["findings"], "review.findings")


def _validate_questions(value: object) -> None:
    fields = {
        "session_id",
        "question",
        "answer",
        "escalate",
        "reason",
        "question_class",
        "authority_reference",
        "status",
    }
    classes = {
        "general",
        "scope",
        "credentials",
        "policy",
        "external_approval",
        "merge",
    }
    if not isinstance(value, list):
        raise CoordinatorError("invalid_state", "questions must be a list")
    for question in value:
        _validate_question_record(strict_mapping(question, fields, "question"), classes)


def _validate_question_record(item: dict, classes: set[str]) -> None:
    _validate_question_fields(item, classes)
    _validate_question_status(item)


def _validate_question_fields(item: dict, classes: set[str]) -> None:
    required = ("session_id", "question", "question_class", "status")
    if not all(
        isinstance(item.get(field), str) and item[field] for field in required
    ):
        raise CoordinatorError("invalid_state", "question record is incomplete")
    if item["question_class"] not in classes:
        raise CoordinatorError("invalid_state", "question class is unsupported")
    if "answer" in item and not isinstance(item["answer"], str):
        raise CoordinatorError("invalid_state", "question answer is invalid")
    if "escalate" in item and not isinstance(item["escalate"], bool):
        raise CoordinatorError("invalid_state", "question escalation is invalid")
    if "reason" in item and not isinstance(item["reason"], str):
        raise CoordinatorError("invalid_state", "question reason is invalid")
    if "authority_reference" in item:
        authority_reference(item["authority_reference"])
    if item["status"] not in QUESTION_RECORD_STATUSES:
        raise CoordinatorError("invalid_state", "question status is invalid")


def _validate_question_status(item: dict) -> None:
    answer = item.get("answer")
    escalated = item.get("escalate") is True
    if item["status"] == "answered" and (
        not isinstance(answer, str)
        or not answer
        or escalated
        or "authority_reference" not in item
    ):
        raise CoordinatorError("invalid_state", "answered question is incompatible")
    if item["status"] == "needs_user" and (
        answer
        and not escalated
        and item["question_class"] not in SENSITIVE_QUESTION_CLASSES
        and "authority_reference" in item
    ):
        raise CoordinatorError(
            "invalid_state", "escalated question is incompatible"
        )


def _validate_discovered_work(value: object) -> None:
    if not isinstance(value, list):
        raise CoordinatorError("invalid_state", "discovered_work must be a list")
    for work in value:
        item = strict_mapping(
            work, {"id", "title", "disposition", "outcome"}, "discovered_work"
        )
        if not isinstance(item.get("id"), str) or item.get("disposition") not in {
            "open",
            "resolved",
            "deferred",
            "excluded",
        }:
            raise CoordinatorError("invalid_state", "discovered work record is invalid")
        if "title" in item and not isinstance(item["title"], str):
            raise CoordinatorError("invalid_state", "discovered work title is invalid")
        if "outcome" in item:
            json_value(item["outcome"], "discovered_work.outcome")


def _validate_gates_and_completion(
    gates_value: object, completion_value: object
) -> None:
    gates = strict_mapping(gates_value, {"integration", "final_verification"}, "gates")
    if not isinstance(gates.get("integration"), list) or not isinstance(
        gates.get("final_verification"), bool
    ):
        raise CoordinatorError("invalid_state", "gates are invalid")
    for gate in gates["integration"]:
        integration_gate(gate)
    completion = strict_mapping(
        completion_value,
        {
            "ready",
            "terminal",
            "review_remediation_required",
            "review_boundary_required",
        },
        "completion",
    )
    required = {
        "ready",
        "terminal",
        "review_remediation_required",
        "review_boundary_required",
    }
    if set(completion) != required or not all(
        isinstance(completion.get(field), bool) for field in required
    ):
        raise CoordinatorError("invalid_state", "completion is invalid")


def validate_state(state: object) -> dict:
    """Validate every durable state record before coordinator use."""
    allowed = {
        "schema_version",
        "revision",
        "phase",
        "next_action",
        "goal_graph",
        "work_items",
        "phase_runs",
        "reviews",
        "questions",
        "discovered_work",
        "gates",
        "capacity",
        "policy",
        "completion",
    }
    data = strict_mapping(state, allowed, "state")
    if set(data) != allowed:
        raise CoordinatorError("invalid_state", "state schema is incomplete")
    if isinstance(data.get("schema_version"), bool) or data.get("schema_version") != 1:
        raise CoordinatorError(
            "unsupported_version", "state schema version is unsupported"
        )
    if (
        not isinstance(data.get("revision"), int)
        or isinstance(data["revision"], bool)
        or data["revision"] < 1
    ):
        raise CoordinatorError("invalid_state", "state revision must be positive")
    if data.get("phase") not in PHASES:
        raise CoordinatorError("invalid_state", "state phase is unsupported")
    if not isinstance(data.get("next_action"), str) or not data["next_action"]:
        raise CoordinatorError("invalid_state", "state next_action must be non-empty")
    if (
        not isinstance(data.get("capacity"), int)
        or isinstance(data["capacity"], bool)
        or data["capacity"] < 1
    ):
        raise CoordinatorError("invalid_state", "state capacity must be positive")
    policy = normalized_policy(data.get("policy"))
    if set(data["policy"]) != POLICY_FIELDS or data["capacity"] != policy["capacity"]:
        raise CoordinatorError("invalid_state", "state policy and capacity disagree")
    nodes = _validate_goal_graph(data.get("goal_graph"), policy)
    _validate_work_items(data.get("work_items"), nodes)
    _validate_phase_runs(data.get("phase_runs"), nodes)
    _validate_reviews(data.get("reviews"))
    _validate_questions(data.get("questions"))
    _validate_discovered_work(data.get("discovered_work"))
    _validate_gates_and_completion(data.get("gates"), data.get("completion"))
    return data
