"""Trust-boundary validation for coordinator input."""

import re
from collections.abc import Mapping

from .errors import CoordinatorError

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
SECRET_WORDS = ("secret", "token", "password", "credential", "private_key", "api_key")


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
    policy = strict_mapping(
        value, {"capacity", "notifications", "merge", "discovered_work"}, "policy"
    )
    if "capacity" in policy and (
        not isinstance(policy["capacity"], int) or policy["capacity"] < 1
    ):
        raise CoordinatorError("invalid_policy", "capacity must be a positive integer")
    return policy


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
