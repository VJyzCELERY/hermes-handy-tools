"""Manage strict, local-only trace records for one issue goal."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 1
PERMISSIONS = (
    "auto",
    "commit",
    "push",
    "pr_create",
    "pr_ready",
    "merge",
    "administrator_merge",
)
FILES = ("goals.config.json", "goals.logs.json", "goals.audit.json")
EVENTS = ("transition", "pause", "resume", "reason", "continuation")
PHASES = (
    "issue",
    "branched",
    "planned",
    "implementing",
    "implemented",
    "awaiting_commit",
    "awaiting_push",
    "pr_open",
    "reviewing",
    "goal_delivered",
)
STAGES = (
    "acquire",
    "branch",
    "plan",
    "implement",
    "deliver",
    "review",
    "remediate",
    "validate",
    "verify",
    "ready",
    "merge",
)
OUTCOMES = ("started", "succeeded", "blocked", "failed", "skipped")
ISSUE_RE = re.compile(
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)#"
    r"(?P<number>[1-9][0-9]*)\Z"
)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
SECRET_RE = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|"
    r"password|credential|authorization|bearer)\b|\bgh[pousr]_[A-Za-z0-9_]{12,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{12,}|\bsk-[A-Za-z0-9_-]{12,})"
)
ENV_ASSIGNMENT_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}=")
URL_QUERY_RE = re.compile(r"https?://\S+\?", re.IGNORECASE)


class TraceError(ValueError):
    """Trace input or persisted data is absent, unsafe, or invalid."""


class ArgumentParser(argparse.ArgumentParser):
    """Argument parser that reports usage errors without exiting."""

    def error(self, message: str) -> None:
        """Raise an exception instead of terminating the process."""
        raise argparse.ArgumentError(None, message)


def _parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("issue")
    for permission in PERMISSIONS:
        init.add_argument(f"--{permission.replace('_', '-')}", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("issue")
    append_log = commands.add_parser("append-log")
    append_log.add_argument("issue")
    append_log.add_argument("--event", required=True)
    append_log.add_argument("--phase", required=True)
    append_log.add_argument("--summary", required=True)
    append_log.add_argument("--reason")
    append_log.add_argument("--resume-action")
    append_audit = commands.add_parser("append-audit")
    append_audit.add_argument("issue")
    append_audit.add_argument("--stage", required=True)
    append_audit.add_argument("--outcome", required=True)
    append_audit.add_argument("--detail", required=True)
    append_audit.add_argument("--reason")
    append_audit.add_argument("--resume-action")
    return parser


def _issue(value: str) -> tuple[str, str]:
    match = ISSUE_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError("issue must be OWNER/REPO#NUMBER")
    goal = f"{match['owner']}/{match['repo']}#{match['number']}".lower()
    key = f"{match['owner']}_{match['repo']}_{match['number']}".lower()
    return goal, key


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise TraceError(f"{field} is too long")
    if CONTROL_RE.search(value):
        raise TraceError(f"{field} contains control characters")
    if SECRET_RE.search(value) or ENV_ASSIGNMENT_RE.search(value) or URL_QUERY_RE.search(value):
        raise TraceError(f"{field} contains token-like or raw environment data")
    return value


def _optional_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _text(value, field, maximum)


def _exact_object(value: object, keys: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise TraceError(f"{field} has unknown or missing fields")
    return value


def _timestamp(value: object, field: str) -> None:
    text = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TraceError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise TraceError(f"{field} must include a timezone")


def _enum(value: object, field: str, allowed: tuple[str, ...]) -> str:
    text = _text(value, field, 64)
    if text not in allowed:
        raise TraceError(f"{field} is invalid")
    return text


def _safe_path(root: Path, path: Path, field: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise TraceError(f"{field} path escapes the repository") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise TraceError(f"{field} path is unsafe")
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise TraceError(f"{field} path escapes the repository") from exc


def _paths(root: Path, key: str) -> tuple[Path, dict[str, Path]]:
    directory = root / ".agents" / "local" / "state" / "goals" / key
    _safe_path(root, directory, "trace directory")
    paths = {name: directory / name for name in FILES}
    for name, path in paths.items():
        _safe_path(root, path, name)
    return directory, paths


def _load_json(path: Path, name: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise TraceError(f"{name} is unsafe")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TraceError(f"{name} is malformed") from exc


def _validate_template(root: Path) -> dict:
    path = root / ".agents" / "templates" / "goals.config.default.json"
    _safe_path(root, path, "default template")
    if path.is_symlink() or not path.is_file():
        raise TraceError("default template is missing or unsafe")
    template = _load_json(path, "default template")
    template = _exact_object(template, {"schema_version", "permissions"}, "default template")
    if template["schema_version"] != SCHEMA_VERSION or isinstance(
        template["schema_version"], bool
    ):
        raise TraceError("default template schema_version is invalid")
    permissions = _exact_object(template["permissions"], set(PERMISSIONS), "permissions")
    for permission in PERMISSIONS:
        if not isinstance(permissions[permission], bool):
            raise TraceError("permissions values must be booleans")
    return template


def _validate_config(value: object, goal: str) -> dict:
    config = _exact_object(
        value,
        {"schema_version", "goal", "recorded_at", "permissions"},
        "goals.config.json",
    )
    if config["schema_version"] != SCHEMA_VERSION or isinstance(
        config["schema_version"], bool
    ):
        raise TraceError("goals.config.json schema_version is invalid")
    if config["goal"] != goal:
        raise TraceError("goals.config.json goal does not match the issue")
    _timestamp(config["recorded_at"], "goals.config.json recorded_at")
    permissions = _exact_object(config["permissions"], set(PERMISSIONS), "permissions")
    for permission in PERMISSIONS:
        if not isinstance(permissions[permission], bool):
            raise TraceError("goals.config.json permissions must be booleans")
    return config


def _validate_logs(value: object, goal: str) -> list[dict]:
    if not isinstance(value, list):
        raise TraceError("goals.logs.json must be a list")
    for index, record in enumerate(value):
        record = _exact_object(
            record,
            {
                "schema_version",
                "goal",
                "at",
                "event",
                "phase",
                "summary",
                "reason",
                "resume_action",
            },
            f"goals.logs.json[{index}]",
        )
        if record["schema_version"] != SCHEMA_VERSION or isinstance(
            record["schema_version"], bool
        ):
            raise TraceError(f"goals.logs.json[{index}] schema_version is invalid")
        if record["goal"] != goal:
            raise TraceError(f"goals.logs.json[{index}] goal does not match the issue")
        _timestamp(record["at"], f"goals.logs.json[{index}] at")
        event = _enum(record["event"], f"goals.logs.json[{index}] event", EVENTS)
        _enum(record["phase"], f"goals.logs.json[{index}] phase", PHASES)
        _text(record["summary"], f"goals.logs.json[{index}] summary", 500)
        reason = _optional_text(record["reason"], f"goals.logs.json[{index}] reason", 500)
        _optional_text(
            record["resume_action"], f"goals.logs.json[{index}] resume_action", 500
        )
        if event == "reason" and reason is None:
            raise TraceError(f"goals.logs.json[{index}] reason is required")
    return value


def _validate_audit(value: object, goal: str) -> list[dict]:
    if not isinstance(value, list):
        raise TraceError("goals.audit.json must be a list")
    for index, record in enumerate(value):
        record = _exact_object(
            record,
            {
                "schema_version",
                "goal",
                "at",
                "stage",
                "outcome",
                "detail",
                "reason",
                "resume_action",
            },
            f"goals.audit.json[{index}]",
        )
        if record["schema_version"] != SCHEMA_VERSION or isinstance(
            record["schema_version"], bool
        ):
            raise TraceError(f"goals.audit.json[{index}] schema_version is invalid")
        if record["goal"] != goal:
            raise TraceError(f"goals.audit.json[{index}] goal does not match the issue")
        _timestamp(record["at"], f"goals.audit.json[{index}] at")
        _enum(record["stage"], f"goals.audit.json[{index}] stage", STAGES)
        _enum(record["outcome"], f"goals.audit.json[{index}] outcome", OUTCOMES)
        _text(record["detail"], f"goals.audit.json[{index}] detail", 4000)
        _optional_text(record["reason"], f"goals.audit.json[{index}] reason", 500)
        _optional_text(
            record["resume_action"], f"goals.audit.json[{index}] resume_action", 500
        )
    return value


def _validate_trace(root: Path, goal: str, key: str) -> tuple[dict, list[dict], list[dict], dict[str, Path]]:
    directory, paths = _paths(root, key)
    if not directory.exists():
        raise TraceError(f"{FILES[0]} is missing")
    if not directory.is_dir():
        raise TraceError("trace directory is missing or unsafe")
    for name, path in paths.items():
        if not path.exists():
            raise TraceError(f"{name} is missing")
    config = _validate_config(_load_json(paths[FILES[0]], FILES[0]), goal)
    logs = _validate_logs(_load_json(paths[FILES[1]], FILES[1]), goal)
    audit = _validate_audit(_load_json(paths[FILES[2]], FILES[2]), goal)
    return config, logs, audit, paths


def _atomic_write(root: Path, path: Path, value: object) -> None:
    _safe_path(root, path.parent, "trace directory")
    if not path.parent.is_dir() or path.is_symlink():
        raise TraceError("trace destination is unsafe")
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _init(args: argparse.Namespace, root: Path, goal: str, key: str) -> dict:
    template = _validate_template(root)
    directory, paths = _paths(root, key)
    existing: dict[str, object] = {}
    for name, path in paths.items():
        if path.is_symlink():
            raise TraceError(f"{name} is unsafe")
        if path.exists():
            existing[name] = _load_json(path, name)
    existing_config: dict | None = None
    if FILES[0] in existing:
        existing_config = _validate_config(existing[FILES[0]], goal)
    if FILES[1] in existing:
        _validate_logs(existing[FILES[1]], goal)
    if FILES[2] in existing:
        _validate_audit(existing[FILES[2]], goal)
    directory.mkdir(parents=True, exist_ok=True)
    _safe_path(root, directory, "trace directory")
    if not directory.is_dir():
        raise TraceError("trace directory is unsafe")
    permissions = {
        permission: bool(getattr(args, permission)) for permission in PERMISSIONS
    }
    if existing_config is None or existing_config["permissions"] != permissions:
        _atomic_write(
            root,
            paths[FILES[0]],
            {
                "schema_version": template["schema_version"],
                "goal": goal,
                "recorded_at": _now(),
                "permissions": permissions,
            },
        )
    for name, value in ((FILES[1], []), (FILES[2], [])):
        if name not in existing:
            _atomic_write(root, paths[name], value)
    return _validate_config(_load_json(paths[FILES[0]], FILES[0]), goal)


def _append_log(args: argparse.Namespace, root: Path, goal: str, key: str) -> list[dict]:
    _, logs, _, paths = _validate_trace(root, goal, key)
    record = {
        "schema_version": SCHEMA_VERSION,
        "goal": goal,
        "at": _now(),
        "event": args.event,
        "phase": args.phase,
        "summary": args.summary,
        "reason": args.reason,
        "resume_action": args.resume_action,
    }
    updated = [*logs, record]
    _validate_logs(updated, goal)
    _atomic_write(root, paths[FILES[1]], updated)
    return updated


def _append_audit(args: argparse.Namespace, root: Path, goal: str, key: str) -> list[dict]:
    _, _, audit, paths = _validate_trace(root, goal, key)
    record = {
        "schema_version": SCHEMA_VERSION,
        "goal": goal,
        "at": _now(),
        "stage": args.stage,
        "outcome": args.outcome,
        "detail": args.detail,
        "reason": args.reason,
        "resume_action": args.resume_action,
    }
    updated = [*audit, record]
    _validate_audit(updated, goal)
    _atomic_write(root, paths[FILES[2]], updated)
    return updated


def _run(args: argparse.Namespace, root: Path) -> object:
    goal, key = _issue(args.issue)
    if args.action == "init":
        return _init(args, root, goal, key)
    if args.action == "validate":
        _validate_trace(root, goal, key)
        return {"goal": goal, "config": "valid", "logs": "valid", "audit": "valid"}
    if args.action == "append-log":
        return _append_log(args, root, goal, key)
    return _append_audit(args, root, goal, key)


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    output: Callable[[str], None] = print,
    error: Callable[[str], None] = print,
) -> int:
    """Run the goal-trace command and return its exit status."""
    try:
        args = _parser().parse_args(argv)
        repository = (root or Path(__file__).resolve().parents[2]).resolve()
        result = _run(args, repository)
        output(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (argparse.ArgumentError, argparse.ArgumentTypeError) as exc:
        error(str(exc))
        return 2
    except (OSError, TraceError) as exc:
        error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
