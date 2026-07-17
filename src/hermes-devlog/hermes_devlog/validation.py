"""Trust-boundary validation for coordinator input."""

import re
from collections.abc import Mapping
from math import isfinite
from pathlib import Path, PurePosixPath

from .errors import CoordinatorError

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
SECRET_WORDS = ("secret", "token", "password", "credential", "private_key", "api_key")
SECRET_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])gh[opsur]_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)-----begin [a-z0-9 ]*private key-----"),
)
WORKER_ROUTES = ("planner", "reviewer", "worker")
PHASES = {
    "issue",
    "plan",
    "implement",
    "implementation_review",
    "remediation",
    "pr_delivery",
    "final_verification",
    "merge_ready",
}
PHASE_RUN_STATUSES = {"running", "completed", "failed", "cancelled"}
QUESTION_STATUSES = {"none", "answered", "needs_user"}
QUESTION_RECORD_STATUSES = {"answered", "needs_user"}
SENSITIVE_QUESTION_CLASSES = {
    "scope",
    "credentials",
    "policy",
    "external_approval",
    "merge",
}
PERMISSION_FIELDS = {
    "claim",
    "implement",
    "commit",
    "push",
    "create_issue",
    "create_pr",
    "post_review",
    "merge",
}
POLICY_FIELDS = {
    "capacity",
    "notifications",
    "discovered_work",
    "auto_merge",
    "require_human_merge_approval",
}
PROFILE_MATCH_RANK = {"native": 0, "adapted": 1, "fallback": 2}


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
    elif isinstance(value, str) and (
        any(word in value.lower() for word in SECRET_WORDS)
        or any(pattern.search(value) for pattern in SECRET_PATTERNS)
    ):
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


def normalized_relative_reference(
    value: object, path: str, error_code: str = "invalid_path"
) -> str:
    """Validate a normalized, traversal-free relative reference."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise CoordinatorError(error_code, f"invalid relative path at {path}")
    reference = PurePosixPath(value)
    if (
        reference.is_absolute()
        or reference.as_posix() != value
        or any(part in {".", ".."} for part in reference.parts)
    ):
        raise CoordinatorError(error_code, f"invalid relative path at {path}")
    return value


def normalized_absolute_path(
    value: object, path: str, error_code: str = "invalid_path"
) -> str:
    """Validate a normalized, absolute, traversal-free filesystem path."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise CoordinatorError(error_code, f"invalid absolute path at {path}")
    candidate = Path(value)
    if (
        not candidate.is_absolute()
        or candidate.as_posix() != value
        or ".." in candidate.parts
    ):
        raise CoordinatorError(error_code, f"invalid absolute path at {path}")
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
    normalized_relative_reference(
        template["snapshot"], "template.snapshot", "invalid_template"
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
    if not isinstance(profile.get("name"), str) or not profile["name"].strip():
        raise CoordinatorError("invalid_profile", "profile name must be non-empty")
    if profile.get("match") not in {"native", "adapted", "fallback"}:
        raise CoordinatorError("invalid_profile", "profile match is unsupported")
    if not isinstance(profile.get("sources"), list) or not all(
        isinstance(item, str) for item in profile["sources"]
    ):
        raise CoordinatorError("invalid_profile", "profile sources must be strings")
    return profile


def _route(value: object) -> dict:
    route = strict_mapping(value, {"model", "reasoning", "agent"}, "route")
    if not {"model", "reasoning"} <= set(route) or not all(
        isinstance(route[field], str) and route[field]
        for field in ("model", "reasoning")
    ):
        raise CoordinatorError(
            "invalid_route", "route fields must be non-empty strings"
        )
    agent = route.get("agent", "opencode")
    identifier(agent, "route.agent")
    return {"model": route["model"], "reasoning": route["reasoning"], "agent": agent}


def _routes(value: object) -> dict:
    """Validate one pinned model route per supported worker role."""
    routes = strict_mapping(value, set(WORKER_ROUTES), "routes")
    if set(routes) != set(WORKER_ROUTES):
        raise CoordinatorError(
            "invalid_routes", "routes must pin planner, reviewer, and worker"
        )
    return {role: _route(route) for role, route in routes.items()}


def _policy(value: object) -> dict:
    policy = strict_mapping(value, POLICY_FIELDS, "policy")
    if "capacity" in policy and (
        not isinstance(policy["capacity"], int)
        or isinstance(policy["capacity"], bool)
        or policy["capacity"] < 1
    ):
        raise CoordinatorError("invalid_policy", "capacity must be a positive integer")
    for field in POLICY_FIELDS - {"capacity"}:
        if field in policy and not isinstance(policy[field], bool):
            raise CoordinatorError("invalid_policy", f"{field} must be boolean")
    return policy


def normalized_policy(value: object) -> dict:
    """Return a complete policy with restrictive autonomous-action defaults."""
    policy_value = dict(value) if isinstance(value, Mapping) else value
    if isinstance(policy_value, dict):
        policy_value.pop("merge", None)
    policy = _policy(policy_value)
    return {
        "capacity": policy.get("capacity", 1),
        "notifications": policy.get("notifications", True),
        "discovered_work": policy.get("discovered_work", True),
        "auto_merge": policy.get("auto_merge", False),
        "require_human_merge_approval": policy.get(
            "require_human_merge_approval", True
        ),
    }


def permission_scope(value: object) -> dict:
    """Validate the fixed executable-authority permission set."""
    if not isinstance(value, Mapping) or not set(value).issubset(PERMISSION_FIELDS):
        raise CoordinatorError(
            "invalid_permissions", "permissions must contain the fixed authority set"
        )
    if not all(isinstance(item, bool) for item in value.values()):
        raise CoordinatorError("invalid_permissions", "permissions must be boolean")
    permissions = {field: bool(value.get(field, False)) for field in PERMISSION_FIELDS}
    if permissions["create_pr"] and not permissions["push"]:
        raise CoordinatorError("invalid_permissions", "create_pr requires push")
    if permissions["push"] and not permissions["commit"]:
        raise CoordinatorError("invalid_permissions", "push requires commit")
    if permissions["merge"] and not permissions["create_pr"]:
        raise CoordinatorError("invalid_permissions", "merge requires create_pr")
    return permissions


def validate_authority(permissions: dict, policy: dict) -> None:
    """Validate policy combinations against fixed executable authority."""
    if policy["auto_merge"] and not permissions["merge"]:
        raise CoordinatorError("invalid_policy", "auto_merge requires merge permission")
    if policy["auto_merge"] and policy["require_human_merge_approval"]:
        raise CoordinatorError(
            "invalid_policy", "auto_merge conflicts with human merge approval"
        )


def goal_payload(value: object, path: str = "goal") -> dict:
    """Validate durable semantic objective and acceptance criteria."""
    data = strict_mapping(value, {"objective", "success_criteria", "approach"}, path)
    if not isinstance(data.get("objective"), str) or not data["objective"].strip():
        raise CoordinatorError("invalid_goal", f"{path}.objective must be non-empty")
    criteria = data.get("success_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise CoordinatorError("invalid_goal", f"{path}.success_criteria is required")
    identifiers = set()
    for item in criteria:
        criterion = strict_mapping(
            item, {"id", "description", "verification"}, f"{path}.success_criteria"
        )
        criterion_id = identifier(criterion.get("id"), f"{path}.success_criteria.id")
        if criterion_id in identifiers:
            raise CoordinatorError(
                "invalid_goal", "success criterion ids must be unique"
            )
        identifiers.add(criterion_id)
        if not all(
            isinstance(criterion.get(field), str) and criterion[field].strip()
            for field in ("description", "verification")
        ):
            raise CoordinatorError("invalid_goal", "success criterion is incomplete")
    approach = data.get("approach", [])
    if not isinstance(approach, list) or not all(
        isinstance(item, str) and item.strip() for item in approach
    ):
        raise CoordinatorError("invalid_goal", f"{path}.approach is invalid")
    data["approach"] = approach
    return data


def governance_payload(value: object) -> dict:
    """Validate additive governance provenance and constraints."""
    data = strict_mapping(value, {"sources", "constraints"}, "governance")
    sources = data.get("sources")
    constraints = data.get("constraints")
    if not isinstance(sources, list) or not isinstance(constraints, list):
        raise CoordinatorError("invalid_governance", "governance lists are required")
    _governance_sources(sources)
    _governance_constraints(constraints)
    return data


def _governance_sources(sources: list) -> None:
    identifiers = set()
    fields = {"id", "kind", "reference", "content_hash", "snapshot_ref", "required"}
    for item in sources:
        source = strict_mapping(item, fields, "governance.source")
        source_id = identifier(source.get("id"), "governance.source.id")
        if source_id in identifiers:
            raise CoordinatorError(
                "invalid_governance", "governance source ids are unique"
            )
        identifiers.add(source_id)
        if not all(
            isinstance(source.get(field), str) and source[field].strip()
            for field in ("kind", "reference")
        ):
            raise CoordinatorError(
                "invalid_governance", "governance source is incomplete"
            )
        content_hash = source.get("content_hash")
        if not isinstance(content_hash, str) or not re.fullmatch(
            r"sha256:[0-9a-fA-F]{64}", content_hash
        ):
            raise CoordinatorError(
                "invalid_governance", "governance source hash is invalid"
            )
        normalized_relative_reference(source.get("snapshot_ref"), "governance.snapshot")
        if not isinstance(source.get("required"), bool):
            raise CoordinatorError(
                "invalid_governance", "governance source required is boolean"
            )


def _governance_constraints(constraints: list) -> None:
    identifiers = set()
    controls = {f"permissions.{field}" for field in PERMISSION_FIELDS}
    controls.update(f"policy.{field}" for field in POLICY_FIELDS)
    fields = {
        "id",
        "kind",
        "statement",
        "applies_to",
        "enforcement",
        "controls",
        "overridable",
    }
    for item in constraints:
        constraint = strict_mapping(item, fields, "governance.constraint")
        constraint_id = identifier(constraint.get("id"), "governance.constraint.id")
        if constraint_id in identifiers:
            raise CoordinatorError(
                "invalid_governance", "governance constraint ids are unique"
            )
        identifiers.add(constraint_id)
        if not all(
            isinstance(constraint.get(field), str) and constraint[field].strip()
            for field in ("kind", "statement", "enforcement")
        ):
            raise CoordinatorError(
                "invalid_governance", "governance constraint is incomplete"
            )
        if not isinstance(constraint.get("applies_to"), list) or not all(
            isinstance(item, str) and item for item in constraint["applies_to"]
        ):
            raise CoordinatorError(
                "invalid_governance", "constraint applies_to is invalid"
            )
        if not isinstance(constraint.get("controls"), list) or not set(
            constraint["controls"]
        ).issubset(controls):
            raise CoordinatorError(
                "invalid_governance", "constraint controls are invalid"
            )
        if not isinstance(constraint.get("overridable"), bool):
            raise CoordinatorError(
                "invalid_governance", "constraint overridable is boolean"
            )


def profile_payload(value: object) -> dict:
    """Validate and return one complete workflow profile."""
    return _profile(value)


def review_identity(value: object, path: str) -> str:
    """Validate a canonical, non-empty review binding identity."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
        or "\x00" in value
    ):
        raise CoordinatorError("invalid_review", f"invalid review identity at {path}")
    return value


def authority_reference(value: object) -> str:
    """Validate a reference to approved state or governing rules."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise CoordinatorError(
            "invalid_question", "authority reference must be a non-empty string"
        )
    source, separator, reference = value.partition(":")
    if not separator or source not in {"state", "rules", "governance"} or not reference:
        raise CoordinatorError(
            "invalid_question",
            "authority reference must name state, rules, or governance",
        )
    if source == "rules":
        normalized_relative_reference(reference, "question.authority_reference")
    elif not re.fullmatch(r"[A-Za-z0-9_.-]+", reference):
        raise CoordinatorError(
            "invalid_question", "state authority reference is invalid"
        )
    return value


def json_value(value: object, path: str) -> None:
    """Require a JSON-compatible value for durable evidence fields."""
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise CoordinatorError(
                "invalid_state", f"{path} contains a non-finite number"
            )
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


def extra_metadata(value: object, path: str = "extra") -> dict:
    """Validate opaque, secret-free JSON metadata without widening schemas."""
    if not isinstance(value, Mapping):
        raise CoordinatorError("invalid_extra", f"{path} must be an object")
    reject_secrets(value, path)
    json_value(value, path)
    return dict(value)


def integration_gate(value: object) -> dict:
    """Validate one bounded integration-gate record."""
    data = strict_mapping(
        value, {"id", "status", "evidence", "extra"}, "integration_gate"
    )
    if not set(data) <= {"id", "status", "evidence", "extra"} or not {
        "id",
        "status",
        "evidence",
    } <= set(data):
        raise CoordinatorError(
            "invalid_gate", "integration gate records require id, status, and evidence"
        )
    identifier(data["id"], "integration_gate.id")
    if data["status"] not in {"open", "resolved"}:
        raise CoordinatorError("invalid_gate", "integration gate status is unsupported")
    json_value(data["evidence"], "integration_gate.evidence")
    if "extra" in data:
        data["extra"] = extra_metadata(data["extra"], "integration_gate.extra")
    return data


def activation_payload(payload: object) -> dict:
    """Validate and normalize activation input."""
    reject_secrets(payload)
    data = strict_mapping(
        payload,
        {
            "goal_id",
            "title",
            "goal",
            "governance",
            "template",
            "profile",
            "routes",
            "permissions",
            "policy",
            "repositories",
            "source_bindings",
            "completion_contract",
            "contract",
            "extra",
        },
        "activation",
    )
    identifier(data.get("goal_id"), "goal_id")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise CoordinatorError("invalid_title", "title must be a non-empty string")
    data["goal"] = goal_payload(
        data.get(
            "goal",
            {
                "objective": data["title"],
                "success_criteria": [
                    {
                        "id": "completion-contract",
                        "description": "Satisfy the declared completion contract.",
                        "verification": "coordinator validation",
                    }
                ],
            },
        )
    )
    data["governance"] = governance_payload(
        data.get("governance", {"sources": [], "constraints": []})
    )
    _template(data.get("template"))
    _profile(data.get("profile"))
    data["routes"] = _routes(data.get("routes"))
    permissions = permission_scope(data.get("permissions"))
    data["permissions"] = permissions
    repositories = data.get("repositories")
    if (
        not isinstance(repositories, list)
        or not repositories
        or not all(isinstance(item, str) and item for item in repositories)
    ):
        raise CoordinatorError(
            "invalid_repositories", "repositories must be a non-empty string list"
        )
    value = data.get("source_bindings")
    if not isinstance(value, (Mapping, list)) or not value:
        raise CoordinatorError(
            "invalid_binding", "source_bindings must be a non-empty object or list"
        )
    json_value(value, "activation.source_bindings")
    contracts = [
        data[field] for field in ("completion_contract", "contract") if field in data
    ]
    if len(contracts) != 1 or not isinstance(contracts[0], Mapping) or not contracts[0]:
        raise CoordinatorError(
            "invalid_binding", "one non-empty completion contract is required"
        )
    json_value(contracts[0], "activation.contract")
    data["policy"] = normalized_policy(data.get("policy", {}))
    validate_authority(permissions, data["policy"])
    if "extra" in data:
        data["extra"] = extra_metadata(data["extra"], "activation.extra")
    return data


def expected_revision(value: object) -> int:
    """Validate a caller's optimistic-concurrency revision."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CoordinatorError(
            "invalid_revision", "expected_revision must be a non-negative integer"
        )
    return value


def validate_state(state: object) -> dict:
    """Validate persisted state through the focused state validator."""
    from .state_validation import validate_state as validate

    return validate(state)


__all__ = [
    "activation_payload",
    "expected_revision",
    "extra_metadata",
    "validate_state",
]
