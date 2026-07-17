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
SUPPORTED_HARNESSES = ("opencode",)
WORKER_ROUTES = ("planner", "reviewer", "worker")
PHASES = {
    "issue",
    "plan",
    "plan_review",
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
POLICY_FIELDS = {"capacity", "notifications", "merge", "discovered_work"}
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
    route = strict_mapping(value, {"model", "variant"}, "route")
    if set(route) != {"model", "variant"} or not all(
        isinstance(item, str) and item for item in route.values()
    ):
        raise CoordinatorError(
            "invalid_route", "route fields must be non-empty strings"
        )
    return route


def _routes(value: object) -> dict:
    """Validate one pinned model route per supported worker role."""
    routes = strict_mapping(value, set(WORKER_ROUTES), "routes")
    if set(routes) != set(WORKER_ROUTES):
        raise CoordinatorError(
            "invalid_routes", "routes must pin planner, reviewer, and worker"
        )
    return {role: _route(route) for role, route in routes.items()}


def _harness(value: object) -> str:
    if value not in SUPPORTED_HARNESSES:
        raise CoordinatorError(
            "invalid_harness", "harness must be one of: opencode"
        )
    return value  # type: ignore[return-value]


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
    """Return a complete policy with restrictive merge defaults."""
    policy = _policy(value)
    return {
        "capacity": policy.get("capacity", 1),
        "notifications": policy.get("notifications", True),
        "merge": policy.get("merge", False),
        "discovered_work": policy.get("discovered_work", True),
    }


def permission_scope(value: object) -> dict:
    """Validate one effective boolean permission scope."""
    if (
        not isinstance(value, Mapping)
        or not value
        or not all(
            isinstance(key, str) and isinstance(item, bool)
            for key, item in value.items()
        )
    ):
        raise CoordinatorError(
            "invalid_permissions", "permissions must be a non-empty boolean object"
        )
    return dict(value)


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
    if not separator or source not in {"state", "rules"} or not reference:
        raise CoordinatorError(
            "invalid_question", "authority reference must name state or rules"
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


def integration_gate(value: object) -> dict:
    """Validate one bounded integration-gate record."""
    data = strict_mapping(value, {"id", "status", "evidence"}, "integration_gate")
    if set(data) != {"id", "status", "evidence"}:
        raise CoordinatorError(
            "invalid_gate", "integration gate records require id, status, and evidence"
        )
    identifier(data["id"], "integration_gate.id")
    if data["status"] not in {"open", "resolved"}:
        raise CoordinatorError("invalid_gate", "integration gate status is unsupported")
    json_value(data["evidence"], "integration_gate.evidence")
    return data


def activation_payload(payload: object) -> dict:
    """Validate and normalize activation input."""
    reject_secrets(payload)
    data = strict_mapping(
        payload,
        {
            "goal_id",
            "title",
            "template",
            "profile",
            "routes",
            "harness",
            "permissions",
            "policy",
            "repositories",
            "source_bindings",
            "completion_contract",
            "contract",
        },
        "activation",
    )
    identifier(data.get("goal_id"), "goal_id")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise CoordinatorError("invalid_title", "title must be a non-empty string")
    _template(data.get("template"))
    _profile(data.get("profile"))
    _routes(data.get("routes"))
    _harness(data.get("harness"))
    permissions = data.get("permissions")
    permission_scope(permissions)
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
    _policy(data.get("policy", {}))
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

__all__ = ["activation_payload", "expected_revision", "validate_state"]
