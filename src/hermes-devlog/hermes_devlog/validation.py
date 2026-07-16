"""Trust-boundary validation for coordinator input."""

import re
from collections.abc import Mapping

from .errors import CoordinatorError

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
SECRET_WORDS = ("secret", "token", "password", "credential", "private_key", "api_key")
PHASES = {
    "issue",
    "plan",
    "implement",
    "implementation_review",
    "remediation",
    "merge_ready",
}
POLICY_FIELDS = {"capacity", "notifications", "merge", "discovered_work"}


def reject_secrets(value: object, path: str = "input") -> None:
    """Reject secret-shaped keys and values before persistence."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            if any(word in key_text for word in SECRET_WORDS):
                raise CoordinatorError(
                    "secret_field", f"secret field is not allowed: {path}.{key}"
                )
            reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(word in value.lower() for word in SECRET_WORDS):
        raise CoordinatorError(
            "secret_value", f"secret-looking value is not allowed at {path}"
        )


def strict_mapping(value: object, allowed: set[str], path: str) -> dict:
    """Require an object with an explicit field allowlist."""
    if not isinstance(value, Mapping):
        raise CoordinatorError("invalid_object", f"{path} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise CoordinatorError(
            "unknown_field", f"unknown field in {path}: {sorted(unknown)[0]}"
        )
    return dict(value)


def identifier(value: object, path: str) -> str:
    """Validate a state path segment or graph identifier."""
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise CoordinatorError("invalid_identifier", f"invalid identifier at {path}")
    return value


def _template(value: object) -> dict:
    template = strict_mapping(
        value, {"release", "commit", "manifest_hash", "snapshot"}, "template"
    )
    if set(template) != {"release", "commit", "manifest_hash", "snapshot"}:
        raise CoordinatorError("invalid_template", "template binding is incomplete")
    if not all(isinstance(item, str) and item for item in template.values()):
        raise CoordinatorError(
            "invalid_template", "template binding fields must be non-empty strings"
        )
    if not SHA1.fullmatch(template["commit"]):
        raise CoordinatorError(
            "invalid_template", "template commit must be a 40-character SHA"
        )
    if not HASH.fullmatch(template["manifest_hash"]):
        raise CoordinatorError(
            "invalid_template", "manifest hash must be a 64-character hash"
        )
    return template


def _profile(value: object) -> dict:
    profile = strict_mapping(value, {"name", "match", "sources"}, "profile")
    if profile.get("match") not in {"native", "adapted", "fallback"}:
        raise CoordinatorError("invalid_profile", "profile match is unsupported")
    if not isinstance(profile.get("sources"), list) or not all(
        isinstance(item, str) for item in profile["sources"]
    ):
        raise CoordinatorError("invalid_profile", "profile sources must be strings")
    return profile


def _route(value: object) -> dict:
    route = strict_mapping(value, {"model", "variant"}, "route")
    if set(route) != {"model", "variant"} or not all(
        isinstance(item, str) and item for item in route.values()
    ):
        raise CoordinatorError(
            "invalid_route", "route fields must be non-empty strings"
        )
    return route


def _policy(value: object) -> dict:
    policy = strict_mapping(value, POLICY_FIELDS, "policy")
    if "capacity" in policy and (
        not isinstance(policy["capacity"], int) or policy["capacity"] < 1
    ):
        raise CoordinatorError("invalid_policy", "capacity must be a positive integer")
    for field in POLICY_FIELDS - {"capacity"}:
        if field in policy and not isinstance(policy[field], bool):
            raise CoordinatorError("invalid_policy", f"{field} must be boolean")
    return policy


def normalized_policy(value: object) -> dict:
    """Return a complete policy with restrictive merge defaults."""
    policy = _policy(value)
    return {
        "capacity": policy.get("capacity", 1),
        "notifications": policy.get("notifications", True),
        "merge": policy.get("merge", False),
        "discovered_work": policy.get("discovered_work", True),
    }


def json_value(value: object, path: str) -> None:
    """Require a JSON-compatible value for durable evidence fields."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            json_value(child, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise CoordinatorError("invalid_state", f"{path} has a non-string key")
            json_value(child, f"{path}.{key}")
        return
    raise CoordinatorError("invalid_state", f"{path} is not JSON-compatible")


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
    if data.get("schema_version") != 1:
        raise CoordinatorError(
            "unsupported_version", "state schema version is unsupported"
        )
    if not isinstance(data.get("revision"), int) or data["revision"] < 1:
        raise CoordinatorError("invalid_state", "state revision must be positive")
    if data.get("phase") not in PHASES:
        raise CoordinatorError("invalid_state", "state phase is unsupported")
    if not isinstance(data.get("next_action"), str) or not data["next_action"]:
        raise CoordinatorError("invalid_state", "state next_action must be non-empty")
    if not isinstance(data.get("capacity"), int) or data["capacity"] < 1:
        raise CoordinatorError("invalid_state", "state capacity must be positive")
    policy = normalized_policy(data.get("policy"))
    if set(data["policy"]) != POLICY_FIELDS:
        raise CoordinatorError("invalid_state", "state policy schema is incomplete")
    if data["capacity"] != policy["capacity"]:
        raise CoordinatorError("invalid_state", "state capacity disagrees with policy")

    graph = strict_mapping(
        data.get("goal_graph"), {"nodes", "dependencies"}, "goal_graph"
    )
    nodes = graph.get("nodes")
    if not isinstance(nodes, Mapping) or not nodes:
        raise CoordinatorError("invalid_state", "goal_graph.nodes must be non-empty")
    for node_id, node_value in nodes.items():
        identifier(node_id, "goal_graph.nodes.key")
        node = strict_mapping(
            node_value,
            {
                "id",
                "title",
                "parent_id",
                "repositories",
                "contract",
                "policy",
                "disposition",
            },
            f"goal_graph.nodes.{node_id}",
        )
        if not {"id", "title", "parent_id", "disposition", "policy"} <= set(node):
            raise CoordinatorError("invalid_state", "goal node schema is incomplete")
        if node.get("id") != node_id or not isinstance(node.get("title"), str):
            raise CoordinatorError(
                "invalid_state", "goal node identity or title is invalid"
            )
        if node.get("parent_id") is not None:
            identifier(node.get("parent_id"), "goal.parent_id")
        if node.get("disposition", "open") not in {
            "open",
            "resolved",
            "deferred",
            "excluded",
        }:
            raise CoordinatorError("invalid_state", "goal disposition is unsupported")
        if "policy" in node:
            _policy(node["policy"])
        if "repositories" in node and (
            not isinstance(node["repositories"], list)
            or not all(isinstance(item, str) for item in node["repositories"])
        ):
            raise CoordinatorError("invalid_state", "goal repositories must be strings")
        if "contract" in node and not isinstance(node["contract"], Mapping):
            raise CoordinatorError("invalid_state", "goal contract must be an object")
    dependencies = graph.get("dependencies")
    if not isinstance(dependencies, list):
        raise CoordinatorError("invalid_state", "goal dependencies must be a list")
    for edge in dependencies:
        item = strict_mapping(edge, {"blocker", "blocked"}, "dependency")
        if not all(isinstance(item.get(key), str) for key in ("blocker", "blocked")):
            raise CoordinatorError(
                "invalid_state", "dependency endpoints must be strings"
            )
        if item["blocker"] not in nodes or item["blocked"] not in nodes:
            raise CoordinatorError("invalid_state", "dependency endpoint is missing")

    if not isinstance(data.get("work_items"), Mapping):
        raise CoordinatorError("invalid_state", "work_items must be an object")
    for key, item in data["work_items"].items():
        identifier(key, "work_items.key")
        if not isinstance(item, Mapping):
            raise CoordinatorError("invalid_state", "work item must be an object")
        json_value(item, f"work_items.{key}")

    phase_run_fields = {
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
    if not isinstance(data.get("phase_runs"), list):
        raise CoordinatorError("invalid_state", "phase_runs must be a list")
    for run in data["phase_runs"]:
        item = strict_mapping(run, phase_run_fields, "phase_run")
        required = phase_run_fields - {"status"}
        if not required <= set(item) or item["phase"] not in PHASES:
            raise CoordinatorError("invalid_state", "phase run is incomplete")
        if (
            not isinstance(item["attempt"], int)
            or isinstance(item["attempt"], bool)
            or item["attempt"] < 1
        ):
            raise CoordinatorError("invalid_state", "phase run attempt is invalid")
        for field in required - {
            "phase",
            "attempt",
            "expected_evidence",
            "observed_evidence",
        }:
            if not isinstance(item[field], str) or not item[field]:
                raise CoordinatorError("invalid_state", f"phase run {field} is invalid")
        json_value(item["expected_evidence"], "phase_run.expected_evidence")
        json_value(item["observed_evidence"], "phase_run.observed_evidence")
        if "status" in item and not isinstance(item["status"], str):
            raise CoordinatorError("invalid_state", "phase run status is invalid")

    if not isinstance(data.get("reviews"), list):
        raise CoordinatorError("invalid_state", "reviews must be a list")
    for review in data["reviews"]:
        item = strict_mapping(
            review, {"head", "base", "diff", "findings", "valid"}, "review"
        )
        if not {"head", "base", "diff", "findings", "valid"} <= set(item):
            raise CoordinatorError("invalid_state", "review is incomplete")
        if not all(isinstance(item[field], str) for field in ("head", "base", "diff")):
            raise CoordinatorError("invalid_state", "review binding is invalid")
        if not isinstance(item["findings"], list) or not isinstance(
            item["valid"], bool
        ):
            raise CoordinatorError("invalid_state", "review record is invalid")
        json_value(item["findings"], "review.findings")

    if not isinstance(data.get("questions"), list):
        raise CoordinatorError("invalid_state", "questions must be a list")
    for question in data["questions"]:
        item = strict_mapping(
            question,
            {
                "session_id",
                "question",
                "answer",
                "escalate",
                "reason",
                "question_class",
                "status",
            },
            "question",
        )
        if not all(
            isinstance(item.get(field), str) and item[field]
            for field in ("session_id", "question", "question_class", "status")
        ):
            raise CoordinatorError("invalid_state", "question record is incomplete")
        if item["question_class"] not in {
            "general",
            "scope",
            "credentials",
            "policy",
            "external_approval",
            "merge",
        }:
            raise CoordinatorError("invalid_state", "question class is unsupported")
        if "answer" in item and not isinstance(item["answer"], str):
            raise CoordinatorError("invalid_state", "question answer is invalid")
        if "escalate" in item and not isinstance(item["escalate"], bool):
            raise CoordinatorError("invalid_state", "question escalation is invalid")
        if "reason" in item and not isinstance(item["reason"], str):
            raise CoordinatorError("invalid_state", "question reason is invalid")

    if not isinstance(data.get("discovered_work"), list):
        raise CoordinatorError("invalid_state", "discovered_work must be a list")
    for work in data["discovered_work"]:
        item = strict_mapping(work, {"id", "title", "disposition"}, "discovered_work")
        if not isinstance(item.get("id"), str) or item.get("disposition") != "open":
            raise CoordinatorError("invalid_state", "discovered work record is invalid")
        if "title" in item and not isinstance(item["title"], str):
            raise CoordinatorError("invalid_state", "discovered work title is invalid")

    gates = strict_mapping(
        data.get("gates"), {"integration", "final_verification"}, "gates"
    )
    if not isinstance(gates.get("integration"), list) or not isinstance(
        gates.get("final_verification"), bool
    ):
        raise CoordinatorError("invalid_state", "gates are invalid")
    completion = strict_mapping(
        data.get("completion"), {"ready", "terminal"}, "completion"
    )
    if not all(
        isinstance(completion.get(field), bool) for field in ("ready", "terminal")
    ):
        raise CoordinatorError("invalid_state", "completion is invalid")
    return data


def activation_payload(payload: object) -> dict:
    """Validate and normalize activation input."""
    reject_secrets(payload)
    data = strict_mapping(
        payload,
        {"goal_id", "title", "template", "profile", "route", "permissions", "policy"},
        "activation",
    )
    identifier(data.get("goal_id"), "goal_id")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise CoordinatorError("invalid_title", "title must be a non-empty string")
    _template(data.get("template"))
    _profile(data.get("profile"))
    _route(data.get("route"))
    permissions = data.get("permissions")
    if (
        not isinstance(permissions, Mapping)
        or not permissions
        or not all(
            isinstance(key, str) and isinstance(item, bool)
            for key, item in permissions.items()
        )
    ):
        raise CoordinatorError(
            "invalid_permissions", "permissions must be a non-empty boolean object"
        )
    _policy(data.get("policy", {}))
    return data


def expected_revision(value: object) -> int:
    """Validate a caller's optimistic-concurrency revision."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CoordinatorError(
            "invalid_revision", "expected_revision must be a non-negative integer"
        )
    return value
