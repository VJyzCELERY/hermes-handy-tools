"""Locked, revision-checked local persistence with a hash-linked audit."""

import fcntl
import hashlib
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .errors import CoordinatorError
from .state_validation import validate_state
from .validation import (
    activation_payload,
    expected_revision,
    extra_metadata,
    identifier,
    reject_secrets,
)

MAX_AUDIT_EVENTS = 100


class StateStore:
    """Persist one coordinator goal below an isolated Hermes home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = root / "state.json"
        self.config_path = root / "config.json"
        self.audit_path = root / "audit"
        self.events_path = self.audit_path / "events"
        self.head_path = self.audit_path / "HEAD.json"
        self.pending_path = root / ".pending.json"
        self.lock_path = root / ".lock"

    @property
    def activity_path(self) -> Path:
        """Return the audit head path retained for internal test compatibility."""
        return self.head_path

    @classmethod
    def from_goal(cls, goal_id: str, home: str | Path | None = None) -> "StateStore":
        """Resolve a validated goal path from HERMES_HOME."""
        identifier(goal_id, "goal_id")
        base = Path(home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        return cls(base / "dev-log" / goal_id)

    @contextmanager
    def locked(self):
        """Hold the per-goal advisory lock."""
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def read(self) -> dict:
        """Read and validate the supported state version."""
        with self.locked():
            self._recover_pending()
            state = self._read_state()
            self._check_audit_matches(state, self._read_config())
            return state

    def read_config(self) -> dict:
        """Read and validate the amendable activation configuration."""
        # note: callers holding the goal lock use this read while mutating state.
        return self._read_config()

    def create(self, config: dict, state: dict) -> dict:
        """Atomically create a goal, refusing accidental overwrite."""
        with self.locked():
            if self.state_path.exists() or self.config_path.exists():
                raise CoordinatorError("already_exists", "goal already exists")
            try:
                self._commit(config, state, "activate")
            except Exception:
                for path in (self.config_path, self.state_path, self.pending_path):
                    path.unlink(missing_ok=True)
                for path in (self.events_path / "1.json", self.head_path):
                    path.unlink(missing_ok=True)
                raise
        return state

    def mutate(
        self,
        revision: int,
        operation: str,
        change: Callable[[dict], dict],
        *,
        actor: str = "hermes",
        verified: bool = True,
        reason: str | None = None,
        target: str = "state",
        change_summary: dict | None = None,
        event_extra: dict | None = None,
    ) -> dict:
        """Apply one revision-checked atomic state mutation."""
        expected = expected_revision(revision)
        with self.locked():
            self._recover_pending()
            self._read_audit()
            state = self._read_state()
            config = self._read_config()
            self._check_revision(state, expected)
            if state["completion"].get("terminal"):
                raise CoordinatorError(
                    "terminal_state", "completed goal state cannot be mutated"
                )
            before = _copy(state)
            updated = change(_copy(state))
            updated["revision"] = expected + 1
            self._validate_state(updated)
            self._validate_state_authority(updated, config)
            self._commit(
                config,
                updated,
                operation,
                actor,
                verified,
                target,
                reason or operation.replace("_", " "),
                change_summary or _state_change(before, updated),
                _digest({"config": config, "state": before}),
                event_extra or {},
            )
        return updated

    def amend_config(
        self,
        revision: int,
        change: Callable[[dict], dict],
        reason: str,
        patch: dict,
        audit_extra: dict,
    ) -> tuple[dict, dict]:
        """Atomically amend validated config and advance the state revision."""
        expected = expected_revision(revision)
        with self.locked():
            self._recover_pending()
            self._read_audit()
            state = self._read_state()
            config = self._read_config()
            self._check_revision(state, expected)
            if state["completion"].get("terminal"):
                raise CoordinatorError(
                    "terminal_state", "completed goal state cannot be mutated"
                )
            before = _copy(config)
            updated_config = change(_copy(config))
            self._validate_config(updated_config)
            self._synchronize_root_authority(state, updated_config)
            state["revision"] = expected + 1
            self._validate_state(state)
            self._validate_state_authority(state, updated_config)
            self._commit(
                updated_config,
                state,
                "amend_config",
                target="config",
                reason=_reason(reason),
                change_summary={
                    "patch": _copy(patch),
                    "fields": _changed(before, updated_config),
                },
                before_digest=_digest({"config": before, "state": state}),
                event_extra=audit_extra,
            )
        return updated_config, state

    def amend_state(
        self,
        revision: int,
        change: Callable[[dict], dict],
        reason: str,
        patch: dict,
        audit_extra: dict,
    ) -> dict:
        """Apply a checked amendment without rewriting phase-run evidence."""
        return self.mutate(
            revision,
            "amend_state",
            change,
            reason=_reason(reason),
            change_summary={"patch": _copy(patch)},
            event_extra=audit_extra,
        )

    def set_next_action(self, action: str, expected_revision: int) -> dict:
        """Persist a scheduler checkpoint with optimistic concurrency."""
        return self.mutate(
            expected_revision,
            "schedule",
            lambda state: {**state, "next_action": action},
        )

    def audit_list(self, limit: int = 20) -> list[dict]:
        """Return a bounded newest-first audit view."""
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= MAX_AUDIT_EVENTS
        ):
            raise CoordinatorError(
                "invalid_limit", f"limit must be between 1 and {MAX_AUDIT_EVENTS}"
            )
        with self.locked():
            head = self._read_audit_head()
            start = max(1, head["revision"] - limit + 1)
            events = [
                self._read_event(revision)
                for revision in range(head["revision"], start - 1, -1)
            ]
        return [_audit_summary(event) for event in events]

    def audit_show(self, revision: int) -> dict:
        """Return one validated audited revision."""
        revision = expected_revision(revision)
        if revision < 1:
            raise CoordinatorError(
                "invalid_revision", "audit revision must be positive"
            )
        with self.locked():
            head = self._read_audit_head()
            if revision > head["revision"]:
                raise CoordinatorError("not_found", "audit revision does not exist")
            return self._read_event(revision)

    def audit_validate(self) -> dict:
        """Validate the audit chain and its current materialized snapshots."""
        with self.locked():
            self._recover_pending()
            events = self._read_audit()
            self._check_audit_matches(self._read_state(), self._read_config(), events)
            return {"valid": True, "revision": events[-1]["revision"]}

    def audit_repair(
        self, revision: int, reason: str, audit_extra: dict
    ) -> tuple[dict, dict]:
        """Restore current files from the last verified immutable audit event."""
        expected = expected_revision(revision)
        with self.locked():
            events = self._read_audit()
            event = events[-1]
            if expected != event["revision"]:
                raise CoordinatorError(
                    "revision_conflict",
                    "expected revision does not match audited state",
                    expected=expected,
                    actual=event["revision"],
                )
            config = _copy(event["config"])
            state = _copy(event["state"])
            state["revision"] = expected + 1
            self._commit(
                config,
                state,
                "audit_repair",
                target="ledger",
                reason=_reason(reason),
                change_summary={"restored_revision": expected},
                before_digest=_digest(
                    {"config": event["config"], "state": event["state"]}
                ),
                event_extra=audit_extra,
            )
        return config, state

    def _read_state(self) -> dict:
        state = self._read_json(self.state_path, "goal state")
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise CoordinatorError(
                "unsupported_version", "state schema version is unsupported"
            )
        return self._validate_state(state)

    def _read_config(self) -> dict:
        config = self._read_json(self.config_path, "goal config")
        if not isinstance(config, dict) or config.get("schema_version") != 1:
            raise CoordinatorError(
                "invalid_state", "goal config version is unsupported"
            )
        self._validate_config(config)
        return config

    def _read_json(self, path: Path, label: str) -> object:
        try:
            return json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise CoordinatorError("not_found", f"{label} does not exist") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoordinatorError("invalid_state", f"{label} cannot be read") from exc

    def _validate_state(self, state: dict) -> dict:
        reject_secrets(state)
        return validate_state(state)

    def _validate_config(self, config: dict) -> dict:
        reject_secrets(config)
        try:
            payload = {
                key: value for key, value in config.items() if key != "schema_version"
            }
            return activation_payload(payload)
        except CoordinatorError as exc:
            raise CoordinatorError("invalid_state", "goal config is invalid") from exc

    def _validate_state_authority(self, state: dict, config: dict) -> None:
        """Reject state amendments that broaden or drift from config authority."""
        root = state["goal_graph"]["nodes"].get(config["goal_id"])
        contract_field = (
            "completion_contract"
            if "completion_contract" in config
            else "contract"
        )
        fields = (
            "permissions",
            "policy",
            "profile",
            "repositories",
            "source_bindings",
            contract_field,
        )
        if not isinstance(root, dict) or root.get("parent_id") is not None or any(
            root.get(field) != config.get(field) for field in fields
        ):
            raise CoordinatorError(
                "invalid_state", "state root authority differs from config"
            )

    def _synchronize_root_authority(self, state: dict, config: dict) -> None:
        """Refresh state fields derived from a valid mutable config amendment."""
        root = state["goal_graph"]["nodes"][config["goal_id"]]
        contract_field = (
            "completion_contract"
            if "completion_contract" in config
            else "contract"
        )
        for field in (
            "permissions",
            "policy",
            "profile",
            "repositories",
            "source_bindings",
            contract_field,
        ):
            root[field] = _copy(config[field])
        state["policy"] = _copy(config["policy"])
        state["capacity"] = config["policy"]["capacity"]

    def _check_revision(self, state: dict, expected: int) -> None:
        if state["revision"] != expected:
            raise CoordinatorError(
                "revision_conflict",
                "expected revision does not match current state",
                expected=expected,
                actual=state["revision"],
            )

    def _commit(
        self,
        config: dict,
        state: dict,
        operation: str,
        actor: str = "hermes",
        verified: bool = True,
        target: str = "ledger",
        reason: str = "ledger mutation",
        change_summary: dict | None = None,
        before_digest: str | None = None,
        event_extra: dict | None = None,
    ) -> None:
        self._validate_config(config)
        self._validate_state(state)
        previous_hash = self._head_hash()
        event = self._event(
            config,
            state,
            operation,
            actor,
            verified,
            previous_hash,
            target,
            _reason(reason),
            change_summary or {"kind": operation},
            before_digest,
            event_extra or {},
        )
        pending = {"config": config, "state": state, "event": event}
        self._atomic_json(self.pending_path, pending)
        self._atomic_json(self.config_path, config)
        self._atomic_json(self.state_path, state)
        self._activity(event)
        self.pending_path.unlink(missing_ok=True)

    def _activity(self, event: dict) -> None:
        """Persist a single immutable event and atomically advance audit HEAD."""
        self._write_event(event)

    def _write_event(self, event: dict) -> None:
        """Write one event without invoking the injectable activity boundary."""
        self.events_path.mkdir(parents=True, exist_ok=True)
        event_path = self.events_path / f"{event['revision']}.json"
        if event_path.exists() and event_path.read_bytes() != _json_bytes(event):
            raise CoordinatorError("invalid_state", "audit event already differs")
        if not event_path.exists():
            self._atomic_json(event_path, event)
        self._atomic_json(
            self.head_path, {"revision": event["revision"], "hash": event["hash"]}
        )

    def _recover_pending(self) -> None:
        if not self.pending_path.exists():
            return
        pending = self._read_json(self.pending_path, "pending audit commit")
        if not isinstance(pending, dict) or set(pending) != {
            "config",
            "state",
            "event",
        }:
            raise CoordinatorError("invalid_state", "pending audit commit is invalid")
        config, state, event = pending["config"], pending["state"], pending["event"]
        if not all(isinstance(item, dict) for item in (config, state, event)):
            raise CoordinatorError("invalid_state", "pending audit commit is invalid")
        self._validate_config(config)
        self._validate_state(state)
        event_path = self.events_path / f"{state['revision']}.json"
        if event_path.exists():
            events = self._read_audit()
            if events[-1] != event:
                raise CoordinatorError(
                    "invalid_state", "pending audit commit is inconsistent"
                )
            self._atomic_json(self.config_path, config)
            self._atomic_json(self.state_path, state)
            self.pending_path.unlink()
            return
        self._validate_event(event, state["revision"], self._head_hash())
        if event["config"] != config or event["state"] != state:
            raise CoordinatorError(
                "invalid_state", "pending audit commit is inconsistent"
            )
        self._atomic_json(self.config_path, config)
        self._atomic_json(self.state_path, state)
        self._write_event(event)
        self.pending_path.unlink()

    def _read_audit_head(self) -> dict:
        """Read only the mutable audit head for bounded audit access."""
        try:
            head = self._read_json(self.head_path, "audit head")
        except CoordinatorError as exc:
            raise CoordinatorError(
                "invalid_state", "audit head cannot be read"
            ) from exc
        if not isinstance(head, dict) or set(head) != {"revision", "hash"}:
            raise CoordinatorError("invalid_state", "audit head is invalid")
        if (
            not isinstance(head["revision"], int)
            or isinstance(head["revision"], bool)
            or head["revision"] < 1
            or not isinstance(head["hash"], str)
        ):
            raise CoordinatorError("invalid_state", "audit head is invalid")
        return head

    def _read_event(self, revision: int) -> dict:
        """Read and authenticate a single audit event without traversing history."""
        event = self._read_json(self.events_path / f"{revision}.json", "audit event")
        if not isinstance(event, dict):
            raise CoordinatorError("invalid_state", "audit event is invalid")
        self._validate_event(event, revision, event.get("previous_hash"))
        return event

    def _read_audit(self) -> list[dict]:
        try:
            head = self._read_json(self.head_path, "audit head")
        except CoordinatorError as exc:
            raise CoordinatorError(
                "invalid_state", "audit head cannot be read"
            ) from exc
        if not isinstance(head, dict) or set(head) != {"revision", "hash"}:
            raise CoordinatorError("invalid_state", "audit head is invalid")
        if (
            not isinstance(head["revision"], int)
            or isinstance(head["revision"], bool)
            or head["revision"] < 1
        ):
            raise CoordinatorError("invalid_state", "audit head is invalid")
        if not isinstance(head["hash"], str):
            raise CoordinatorError("invalid_state", "audit head is invalid")
        events = []
        previous_hash = None
        for revision in range(1, head["revision"] + 1):
            event_path = self.events_path / f"{revision}.json"
            event = self._read_json(event_path, "audit event")
            self._validate_event(event, revision, previous_hash)
            events.append(event)
            previous_hash = event["hash"]
        if previous_hash != head["hash"]:
            raise CoordinatorError(
                "invalid_state", "audit head hash does not match events"
            )
        return events

    def _check_audit_matches(
        self, state: dict, config: dict, events: list[dict] | None = None
    ) -> None:
        events = events or self._read_audit()
        if events[-1]["state"] != state or events[-1]["config"] != config:
            raise CoordinatorError(
                "invalid_state", "materialized ledger differs from audit"
            )

    def _head_hash(self) -> str | None:
        if not self.head_path.exists():
            return None
        head = self._read_json(self.head_path, "audit head")
        if (
            not isinstance(head, dict)
            or set(head) != {"revision", "hash"}
            or not isinstance(head["hash"], str)
        ):
            raise CoordinatorError("invalid_state", "audit head is invalid")
        return head["hash"]

    def _event(
        self,
        config: dict,
        state: dict,
        operation: str,
        actor: str,
        verified: bool,
        previous_hash: str | None,
        target: str,
        reason: str,
        change_summary: dict,
        before_digest: str | None,
        event_extra: dict,
    ) -> dict:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "operation": operation,
            "revision": state["revision"],
            "verified": verified,
            "previous_hash": previous_hash,
            "target": target,
            "reason": reason,
            "change": change_summary,
            "before_digest": before_digest,
            "after_digest": _digest({"config": config, "state": state}),
            "extra": _copy(event_extra),
            "config": _copy(config),
            "state": _copy(state),
        }
        event["hash"] = _hash(event)
        return event

    def _validate_event(
        self, event: object, revision: int, previous_hash: str | None
    ) -> None:
        fields = {
            "timestamp",
            "actor",
            "operation",
            "revision",
            "verified",
            "previous_hash",
            "config",
            "state",
            "hash",
            "target",
            "reason",
            "change",
            "before_digest",
            "after_digest",
            "extra",
        }
        if not isinstance(event, dict) or set(event) != fields:
            raise CoordinatorError("invalid_state", "audit event is invalid")
        if (
            not isinstance(event["timestamp"], str)
            or not event["timestamp"]
            or not isinstance(event["actor"], str)
            or not event["actor"]
            or not isinstance(event["operation"], str)
            or not event["operation"]
            or event["revision"] != revision
            or not isinstance(event["verified"], bool)
            or event["previous_hash"] != previous_hash
            or not isinstance(event["hash"], str)
            or not isinstance(event["target"], str)
            or not event["target"]
            or not isinstance(event["reason"], str)
            or not event["reason"]
            or not isinstance(event["change"], dict)
            or not isinstance(event["before_digest"], (str, type(None)))
            or event["after_digest"]
            != _digest({"config": event["config"], "state": event["state"]})
            or event["hash"]
            != _hash({key: value for key, value in event.items() if key != "hash"})
            or not isinstance(event["config"], dict)
            or not isinstance(event["state"], dict)
        ):
            raise CoordinatorError("invalid_state", "audit event is invalid")
        self._validate_config(event["config"])
        self._validate_state(event["state"])
        reject_secrets(event["change"])
        extra_metadata(event["extra"], "audit.extra")
        if event["state"]["revision"] != revision:
            raise CoordinatorError("invalid_state", "audit event revision is invalid")

    def _atomic_json(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_bytes(_json_bytes(value))
        temporary.replace(path)


def _copy(value: dict) -> dict:
    return json.loads(json.dumps(value, allow_nan=False))


def _json_bytes(value: dict) -> bytes:
    serialized = json.dumps(value, allow_nan=False, indent=2, sort_keys=True)
    return f"{serialized}\n".encode()


def _hash(event: dict) -> str:
    return hashlib.sha256(_json_bytes(event)).hexdigest()


def _digest(value: dict) -> str:
    """Return a canonical digest for audit before/after comparison."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _reason(value: object) -> str:
    """Require an auditable human-readable correction reason."""
    if not isinstance(value, str) or not value.strip():
        raise CoordinatorError("invalid_reason", "reason must be a non-empty string")
    return value


def _changed(before: dict, after: dict) -> list[str]:
    """Return stable top-level keys changed by one mutation."""
    return sorted(key for key in before | after if before.get(key) != after.get(key))


def _state_change(before: dict, after: dict) -> dict:
    """Summarize ordinary coordinator mutations without embedding snapshots."""
    return {"fields": _changed(before, after)}


def _audit_summary(event: dict) -> dict:
    """Return the list-safe projection of an otherwise replayable event."""
    return {
        key: event[key]
        for key in (
            "timestamp",
            "actor",
            "operation",
            "revision",
            "verified",
            "previous_hash",
            "hash",
            "target",
            "reason",
            "change",
            "before_digest",
            "after_digest",
            "extra",
        )
    }
