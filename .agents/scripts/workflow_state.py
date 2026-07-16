"""Manage versioned, repository-local workflow state for one issue."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 4
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
STATUSES = ("active", "paused", "needs_user", "blocked", "goal_delivered", "complete")
RESUMABLE_STATUSES = {"active", "paused", "needs_user", "blocked"}
REVIEW_STATES = {"ACTIVE_OPEN", "COMPLETE", "CLEAN", "ARCHIVED"}
ARTIFACTS = ("directory", "spec", "design", "plan", "task", "branch_breakdown")
SPECS_DOCUMENTS = ("spec", "design", "plan", "task")
STATE_KEYS = {
    "schema_version",
    "repository",
    "issue",
    "objective",
    "phase",
    "status",
    "branch",
    "artifacts",
    "specs",
    "prs",
    "review",
    "pending_action",
    "environment_retry",
    "created_at",
    "updated_at",
}
LEGACY_STATE_KEYS = STATE_KEYS - {"environment_retry"}
TRANSITIONS = {(phase, phase) for phase in PHASES} | set(zip(PHASES, PHASES[1:]))
ISSUE_RE = re.compile(
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)#"
    r"(?P<number>[1-9][0-9]*)\Z"
)
PR_RE = re.compile(
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)!"
    r"(?P<number>[1-9][0-9]*)\Z"
)
PR_STATE_KEYS = (LEGACY_STATE_KEYS - {"issue"}) | {"target", "plan_head"}


class StateError(ValueError):
    """Workflow state is absent, unsafe, or invalid."""


class ArgumentParser(argparse.ArgumentParser):
    """Argument parser that reports usage errors without exiting."""

    def error(self, message: str) -> None:
        """Raise an exception instead of terminating the process."""
        raise argparse.ArgumentError(None, message)


def _parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    resolve = commands.add_parser("resolve-active")
    resolve.add_argument("--format", choices=("human", "json"), default="human")
    for action in ("show", "clear"):
        command = commands.add_parser(action)
        command.add_argument("issue")
        if action == "show":
            command.add_argument("--format", choices=("human", "json"), default="human")

    init = commands.add_parser("init")
    init.add_argument("issue")
    init.add_argument("--title", required=True)
    init.add_argument("--url", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--format", choices=("human", "json"), default="human")

    init_pr = commands.add_parser("init-pr")
    init_pr.add_argument("target")
    init_pr.add_argument("--title", required=True)
    init_pr.add_argument("--url", required=True)
    init_pr.add_argument("--head", required=True)
    init_pr.add_argument("--format", choices=("human", "json"), default="human")

    plan_head = commands.add_parser("set-plan-head")
    plan_head.add_argument("target")
    plan_head.add_argument("--head", required=True)
    plan_head.add_argument("--format", choices=("human", "json"), default="human")

    validate_plan = commands.add_parser("validate-plan-head")
    validate_plan.add_argument("target")
    validate_plan.add_argument("--head", required=True)
    validate_plan.add_argument("--format", choices=("human", "json"), default="human")

    transition = commands.add_parser("transition")
    transition.add_argument("issue")
    transition.add_argument("phase", nargs="?", choices=PHASES)
    transition.add_argument("--phase", dest="phase_option", choices=PHASES)
    transition.add_argument("--status", choices=STATUSES)
    pending_action = transition.add_mutually_exclusive_group()
    pending_action.add_argument("--pending-action")
    pending_action.add_argument("--clear-pending-action", action="store_true")
    transition.add_argument("--format", choices=("human", "json"), default="human")

    branch = commands.add_parser("set-branch")
    branch.add_argument("issue")
    branch.add_argument("name")
    branch.add_argument("--base", required=True)
    branch.add_argument("--format", choices=("human", "json"), default="human")

    artifacts = commands.add_parser("set-artifacts")
    artifacts.add_argument("issue")
    for name in ARTIFACTS:
        artifacts.add_argument(f"--{name.replace('_', '-')}", dest=name)
    artifacts.add_argument("--format", choices=("human", "json"), default="human")

    specs = commands.add_parser("set-specs")
    specs.add_argument("issue")
    specs.add_argument("--number", required=True, type=int)
    specs.add_argument("--url", required=True)
    specs.add_argument("--index-url", required=True)
    specs.add_argument("--revision", required=True, type=int)
    for name in SPECS_DOCUMENTS:
        specs.add_argument(f"--{name}-url", required=True)
    specs.add_argument("--format", choices=("human", "json"), default="human")

    pr = commands.add_parser("set-pr")
    pr.add_argument("issue")
    pr.add_argument("number", type=int)
    pr.add_argument("--url", required=True)
    pr.add_argument("--head", required=True)
    pr.add_argument("--base", required=True)
    pr.add_argument("--format", choices=("human", "json"), default="human")

    review = commands.add_parser("set-review")
    review.add_argument("issue")
    review.add_argument("report")
    review.add_argument("--state", required=True)
    review.add_argument("--archive")
    review.add_argument("--format", choices=("human", "json"), default="human")

    retry = commands.add_parser("record-environment-failure")
    retry.add_argument("issue")
    retry.add_argument("--fingerprint", required=True)
    retry.add_argument("--resume-action", required=True)
    retry.add_argument("--format", choices=("human", "json"), default="human")

    reset_retry = commands.add_parser("reset-environment-retry")
    reset_retry.add_argument("issue")
    reset_retry.add_argument("--format", choices=("human", "json"), default="human")
    return parser


def _issue(value: str) -> dict[str, str | int]:
    match = ISSUE_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError("issue must be OWNER/REPO#NUMBER")
    return {
        "owner": match["owner"],
        "repo": match["repo"],
        "number": int(match["number"]),
    }


def _issue_text(repository: str, number: int) -> str:
    return f"{repository}#{number}"


def _pr(value: str) -> dict[str, str | int]:
    match = PR_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError("PR target must be OWNER/REPO!NUMBER")
    return {
        "owner": match["owner"],
        "repo": match["repo"],
        "number": int(match["number"]),
    }


def _pr_text(repository: str, number: int) -> str:
    return f"{repository}!{number}"


def _state_path(root: Path, issue: dict[str, str | int]) -> Path:
    key = f"{issue['owner']}_{issue['repo']}_{issue['number']}".lower()
    return root / ".agents" / "local" / "state" / "goals" / f"{key}.json"


def _pr_state_path(root: Path, target: dict[str, str | int]) -> Path:
    key = f"{target['owner']}_{target['repo']}_pr_{target['number']}".lower()
    return root / ".agents" / "local" / "state" / "goals" / f"{key}.json"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{field} must be a non-empty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _relative_path(root: Path, value: object, field: str) -> str:
    text = _text(value, field)
    if Path(text).is_absolute():
        raise StateError(f"{field} must be a repository-relative path")
    try:
        (root / text).resolve().relative_to(root)
    except ValueError as exc:
        raise StateError(f"{field} path escapes the repository") from exc
    return Path(text).as_posix()


def _object(value: object, keys: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise StateError(f"{field} has unknown or missing fields")
    return value


def _timestamp(value: object, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise StateError(f"{field} must include a timezone")
    return parsed


def _validate(root: Path, state: object, expected: dict[str, str | int]) -> dict:
    if not isinstance(state, dict):
        raise StateError("state has unknown or missing fields")
    legacy = state.get("schema_version") == 2 and not isinstance(
        state.get("schema_version"), bool
    )
    if legacy and "specs" not in state:
        state = state | {"specs": None}
    state = _object(state, LEGACY_STATE_KEYS if legacy else STATE_KEYS, "state")
    if state["schema_version"] not in {2, SCHEMA_VERSION} or isinstance(
        state["schema_version"], bool
    ):
        raise StateError(f"unsupported schema version: {state['schema_version']!r}")
    repository = _text(state["repository"], "repository")
    issue = _object(state["issue"], {"number", "url", "title"}, "issue")
    number = issue["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise StateError("issue.number must be a positive integer")
    expected_repository = f"{expected['owner']}/{expected['repo']}"
    if (
        repository.lower() != expected_repository.lower()
        or number != expected["number"]
    ):
        raise StateError("state issue does not match its file")
    _text(issue["url"], "issue.url")
    _text(issue["title"], "issue.title")
    _text(state["objective"], "objective")
    if state["phase"] not in PHASES or state["status"] not in STATUSES:
        raise StateError("state has an invalid phase or status")
    delivered = state["phase"] == "goal_delivered"
    delivered_status = state["status"] in {"goal_delivered", "complete"}
    if delivered != delivered_status:
        raise StateError("state has an invalid phase/status combination")
    branch = _object(state["branch"], {"name", "base"}, "branch")
    for name, value in branch.items():
        _optional_text(value, f"branch.{name}")
    artifacts = _object(state["artifacts"], set(ARTIFACTS), "artifacts")
    for name, value in artifacts.items():
        if value is not None:
            artifacts[name] = _relative_path(root, value, f"artifacts.{name}")
    state["specs"] = _specs(state["specs"], repository)
    if not isinstance(state["prs"], list):
        raise StateError("prs must be a list")
    heads: set[str] = set()
    numbers: set[int] = set()
    urls: set[str] = set()
    for index, value in enumerate(state["prs"]):
        pr = _object(value, {"number", "url", "head", "base"}, f"prs[{index}]")
        if (
            not isinstance(pr["number"], int)
            or isinstance(pr["number"], bool)
            or pr["number"] < 1
        ):
            raise StateError(f"prs[{index}].number must be a positive integer")
        for name in ("url", "head", "base"):
            _text(pr[name], f"prs[{index}].{name}")
        if pr["head"] in heads or pr["number"] in numbers or pr["url"] in urls:
            raise StateError("prs must contain unique head, number, and URL values")
        heads.add(pr["head"])
        numbers.add(pr["number"])
        urls.add(pr["url"])
    if state["review"] is not None:
        review = _object(state["review"], {"report", "state", "archive"}, "review")
        review["report"] = _relative_path(root, review["report"], "review.report")
        if review["state"] not in REVIEW_STATES:
            raise StateError("review.state is invalid")
        if review["archive"] is not None:
            review["archive"] = _relative_path(
                root, review["archive"], "review.archive"
            )
        if review["state"] == "ARCHIVED" and review["archive"] is None:
            raise StateError("review.archive is required for ARCHIVED review state")
    if delivered and (
        state["review"] is None or state["review"]["state"] not in {"CLEAN", "ARCHIVED"}
    ):
        raise StateError("goal_delivered requires CLEAN or ARCHIVED review evidence")
    _optional_text(state["pending_action"], "pending_action")
    if not legacy:
        retry = _object(
            state["environment_retry"],
            {"fingerprint", "consecutive_count"},
            "environment_retry",
        )
        count = retry["consecutive_count"]
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 5:
            raise StateError("environment_retry.consecutive_count must be between 0 and 5")
        if count == 0:
            if retry["fingerprint"] is not None:
                raise StateError("environment_retry.fingerprint must be null when count is zero")
        else:
            _text(retry["fingerprint"], "environment_retry.fingerprint")
    created = _timestamp(state["created_at"], "created_at")
    updated = _timestamp(state["updated_at"], "updated_at")
    if updated < created:
        raise StateError("updated_at cannot precede created_at")
    return state


def _specs(value: object, repository: str) -> dict | None:
    """Validate the complete remote planning record for one repository."""
    if value is None:
        return None
    specs = _object(
        value,
        {"number", "url", "index_url", "revision", "documents"},
        "specs",
    )
    number = specs["number"]
    revision = specs["revision"]
    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or number < 1
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
    ):
        raise StateError("specs number and revision must be positive integers")
    base = f"https://github.com/{repository}/issues/{number}"
    if _text(specs["url"], "specs.url").lower() != base.lower():
        raise StateError("specs.url must identify the repository Specs issue")
    if _text(specs["index_url"], "specs.index_url").lower() != base.lower():
        raise StateError("specs.index_url must identify the repository Specs issue")
    documents = _object(specs["documents"], set(SPECS_DOCUMENTS), "specs.documents")
    for name, url in documents.items():
        text = _text(url, f"specs.documents.{name}")
        if not re.fullmatch(re.escape(base) + r"#issuecomment-[1-9][0-9]*", text, re.I):
            raise StateError("specs documents must be comments on the Specs issue")
    return specs


def _head(value: object, field: str) -> str:
    text = _text(value, field)
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise StateError(f"{field} must be a 40-character lowercase Git SHA")
    return text


def _validate_pr(root: Path, state: object, expected: dict[str, str | int]) -> dict:
    state = _object(state, PR_STATE_KEYS, "state")
    if state["schema_version"] != 3:
        raise StateError(f"unsupported schema version: {state['schema_version']!r}")
    repository = _text(state["repository"], "repository")
    expected_repository = f"{expected['owner']}/{expected['repo']}"
    if repository.lower() != expected_repository.lower():
        raise StateError("state target does not match its file")
    target = _object(state["target"], {"number", "url", "title", "head"}, "target")
    if target["number"] != expected["number"] or isinstance(target["number"], bool):
        raise StateError("state target does not match its file")
    _text(target["url"], "target.url")
    _text(target["title"], "target.title")
    _head(target["head"], "target.head")
    state["plan_head"] = _optional_text(state["plan_head"], "plan_head")
    if state["plan_head"] is not None:
        _head(state["plan_head"], "plan_head")

    legacy = dict(state)
    legacy["schema_version"] = 2
    legacy["issue"] = {
        "number": target["number"],
        "url": target["url"],
        "title": target["title"],
    }
    legacy.pop("target")
    legacy.pop("plan_head")
    _validate(root, legacy, expected)
    return state


def _migrate_issue_state(state: object) -> dict:
    """Upgrade prior issue workflow schemas to the current shape."""
    if not isinstance(state, dict):
        raise StateError("state has unknown or missing fields")
    if state.get("schema_version") == 2:
        state["schema_version"] = SCHEMA_VERSION
        state.setdefault("specs", None)
        state["environment_retry"] = {"fingerprint": None, "consecutive_count": 0}
    elif state.get("schema_version") == 3:
        state["schema_version"] = SCHEMA_VERSION
        state.setdefault("specs", None)
    return state


def _migrate_pr_state(state: object) -> dict:
    """Add remote Specs state to prior direct PR workflow records."""
    if not isinstance(state, dict):
        raise StateError("state has unknown or missing fields")
    if state.get("schema_version") == 3:
        state.setdefault("specs", None)
    return state


def _load(root: Path, issue: dict[str, str | int]) -> tuple[Path, dict]:
    path = _state_path(root, issue)
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise StateError("state path escapes the repository") from exc
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        repository = f"{issue['owner']}/{issue['repo']}"
        raise StateError(
            f"state not found for {_issue_text(repository, issue['number'])}"
        ) from exc
    try:
        state = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError(f"malformed state JSON: {exc}") from exc
    return path, _validate(root, _migrate_issue_state(state), issue)


def _load_pr(root: Path, target: dict[str, str | int]) -> tuple[Path, dict]:
    path = _pr_state_path(root, target)
    try:
        path.resolve().relative_to(root)
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        repository = f"{target['owner']}/{target['repo']}"
        raise StateError(
            f"state not found for {_pr_text(repository, target['number'])}"
        ) from exc
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError(f"malformed PR state: {exc}") from exc
    return path, _validate_pr(root, _migrate_pr_state(state), target)


def _resolve_active(root: Path) -> dict:
    directory = root / ".agents" / "local" / "state" / "goals"
    if not directory.exists():
        raise StateError("no active workflow state found")
    try:
        directory.resolve().relative_to(root)
    except ValueError as exc:
        raise StateError("state directory escapes the repository") from exc
    states = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "target" in raw:
                raw = _migrate_pr_state(raw)
                raw = _object(raw, PR_STATE_KEYS, "state")
                repository = _text(raw["repository"], "repository")
                target_data = _object(
                    raw["target"], {"number", "url", "title", "head"}, "target"
                )
                target = _pr(_pr_text(repository, target_data["number"]))
                state = _validate_pr(root, raw, target)
                if path.resolve() != _pr_state_path(root, target).resolve():
                    raise StateError(f"state file has a noncanonical name: {path.name}")
            else:
                raw = _migrate_issue_state(raw)
                legacy = isinstance(raw, dict) and raw.get("schema_version") == 2
                raw = _object(raw, LEGACY_STATE_KEYS if legacy else STATE_KEYS, "state")
                repository = _text(raw["repository"], "repository")
                issue_data = _object(raw["issue"], {"number", "url", "title"}, "issue")
                issue = _issue(_issue_text(repository, issue_data["number"]))
                state = _validate(root, raw, issue)
                if path.resolve() != _state_path(root, issue).resolve():
                    raise StateError(f"state file has a noncanonical name: {path.name}")
        except (
            argparse.ArgumentTypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise StateError(f"invalid workflow state {path.name}: {exc}") from exc
        if state["status"] in RESUMABLE_STATUSES:
            states.append(state)
    if not states:
        raise StateError("no active workflow state found")
    if len(states) != 1:
        raise StateError("multiple active workflow states found")
    return states[0]


def _write(root: Path, path: Path, state: dict) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved_parent = parent.resolve()
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise StateError("state directory escapes the repository") from exc
    data = json.dumps(state, indent=2, sort_keys=True) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=resolved_parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _render(state: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(state, indent=2, sort_keys=True)
    identity = (
        _pr_text(state["repository"], state["target"]["number"])
        if "target" in state
        else _issue_text(state["repository"], state["issue"]["number"])
    )
    return f"{identity}: {state['phase']} ({state['status']})"


def _new_state(args: argparse.Namespace, issue: dict[str, str | int]) -> dict:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": f"{issue['owner']}/{issue['repo']}",
        "issue": {"number": issue["number"], "url": args.url, "title": args.title},
        "objective": args.objective,
        "phase": "issue",
        "status": "active",
        "branch": {"name": None, "base": None},
        "artifacts": dict.fromkeys(ARTIFACTS),
        "specs": None,
        "prs": [],
        "review": None,
        "pending_action": None,
        "environment_retry": {"fingerprint": None, "consecutive_count": 0},
        "created_at": now,
        "updated_at": now,
    }


def _new_pr_state(args: argparse.Namespace, target: dict[str, str | int]) -> dict:
    now = _now()
    return {
        "schema_version": 3,
        "repository": f"{target['owner']}/{target['repo']}",
        "target": {
            "number": target["number"],
            "url": args.url,
            "title": args.title,
            "head": args.head,
        },
        "objective": args.title,
        "phase": "issue",
        "status": "active",
        "branch": {"name": None, "base": None},
        "artifacts": dict.fromkeys(ARTIFACTS),
        "specs": None,
        "prs": [],
        "review": None,
        "pending_action": None,
        "plan_head": None,
        "created_at": now,
        "updated_at": now,
    }


def _mutate(args: argparse.Namespace, root: Path, state: dict) -> None:
    allowed_phases = {
        "set-branch": {"issue", "branched"},
        "set-artifacts": {"branched", "planned"},
        "set-specs": {"branched", "planned"},
        "set-pr": {"awaiting_push", "pr_open", "reviewing"},
        "set-review": {"pr_open", "reviewing", "goal_delivered"},
    }
    if (
        args.action in allowed_phases
        and state["phase"] not in allowed_phases[args.action]
    ):
        raise StateError(f"{args.action} is not allowed during phase {state['phase']}")
    if args.action == "transition":
        if args.phase and args.phase_option and args.phase != args.phase_option:
            raise StateError("phase was specified twice with different values")
        phase = args.phase_option or args.phase or state["phase"]
        if (state["phase"], phase) not in TRANSITIONS:
            raise StateError("invalid workflow transition")
        state["phase"] = phase
        if args.status is not None:
            state["status"] = args.status
        if args.pending_action is not None:
            state["pending_action"] = _text(args.pending_action, "pending_action")
        elif args.clear_pending_action:
            state["pending_action"] = None
    elif args.action == "set-branch":
        state["branch"] = {
            "name": _text(args.name, "branch.name"),
            "base": _text(args.base, "branch.base"),
        }
    elif args.action == "set-artifacts":
        updates = {
            name: getattr(args, name) for name in ARTIFACTS if getattr(args, name)
        }
        if not updates:
            raise StateError("at least one artifact is required")
        state["artifacts"].update(
            {
                name: _relative_path(root, value, f"artifacts.{name}")
                for name, value in updates.items()
            }
        )
    elif args.action == "set-specs":
        state["specs"] = _specs(
            {
                "number": args.number,
                "url": args.url,
                "index_url": args.index_url,
                "revision": args.revision,
                "documents": {
                    name: getattr(args, f"{name}_url") for name in SPECS_DOCUMENTS
                },
            },
            state["repository"],
        )
    elif args.action == "set-pr":
        if args.number < 1:
            raise StateError("pr.number must be a positive integer")
        pr = {
            "number": args.number,
            "url": _text(args.url, "pr.url"),
            "head": _text(args.head, "pr.head"),
            "base": _text(args.base, "pr.base"),
        }
        for index, existing in enumerate(state["prs"]):
            if existing["number"] == pr["number"]:
                state["prs"][index] = pr
                break
        else:
            state["prs"].append(pr)
    elif args.action == "set-review":
        state["review"] = {
            "report": _relative_path(root, args.report, "review.report"),
            "state": _text(args.state, "review.state"),
            "archive": (
                _relative_path(root, args.archive, "review.archive")
                if args.archive
                else None
            ),
        }
    elif args.action == "record-environment-failure":
        fingerprint = _text(args.fingerprint, "environment failure fingerprint")
        resume_action = _text(args.resume_action, "environment failure resume action")
        retry = state["environment_retry"]
        retry["consecutive_count"] = min(
            retry["consecutive_count"] + 1 if retry["fingerprint"] == fingerprint else 1,
            5,
        )
        retry["fingerprint"] = fingerprint
        if retry["consecutive_count"] == 5:
            state["status"] = "blocked"
            state["pending_action"] = (
                "Environment failure after 5 consecutive identical attempts "
                f"({fingerprint}): {resume_action}"
            )
    elif args.action == "reset-environment-retry":
        state["environment_retry"] = {"fingerprint": None, "consecutive_count": 0}


def _run(args: argparse.Namespace, root: Path) -> dict | None:
    if args.action == "resolve-active":
        return _resolve_active(root)
    if args.action in {"init-pr", "set-plan-head", "validate-plan-head"}:
        target = _pr(args.target)
        path = _pr_state_path(root, target)
        if args.action == "init-pr":
            if path.exists():
                return _load_pr(root, target)[1]
            state = _new_pr_state(args, target)
            _validate_pr(root, state, target)
            _write(root, path, state)
            return state
        path, state = _load_pr(root, target)
        if args.action == "set-plan-head":
            state["plan_head"] = _head(args.head, "plan_head")
            state["updated_at"] = _now()
            _validate_pr(root, state, target)
            _write(root, path, state)
            return state
        expected = _head(args.head, "head")
        if state["plan_head"] != expected:
            raise StateError("plan is stale for the current PR head")
        return state
    issue = _issue(args.issue)
    path = _state_path(root, issue)
    if args.action == "show":
        return _load(root, issue)[1]
    if args.action == "init":
        if path.exists():
            return _load(root, issue)[1]
        state = _new_state(args, issue)
        _validate(root, state, issue)
        _write(root, path, state)
        return state
    if args.action == "clear":
        try:
            path.parent.resolve().relative_to(root)
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise StateError("state path escapes the repository") from exc
        path.unlink(missing_ok=True)
        return None
    path, state = _load(root, issue)
    state = _migrate_issue_state(state)
    _mutate(args, root, state)
    state["updated_at"] = _now()
    _validate(root, state, issue)
    _write(root, path, state)
    return state


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    output: Callable[[str], None] = print,
    error: Callable[[str], None] = print,
) -> int:
    """Run the workflow-state command and return its exit status."""
    try:
        args = _parser().parse_args(argv)
        repository = (root or Path(__file__).resolve().parents[2]).resolve()
        state = _run(args, repository)
        if state is not None:
            output(_render(state, getattr(args, "format", "human")))
        return 0
    except (argparse.ArgumentError, argparse.ArgumentTypeError) as exc:
        error(str(exc))
        return 2
    except (OSError, StateError) as exc:
        error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
