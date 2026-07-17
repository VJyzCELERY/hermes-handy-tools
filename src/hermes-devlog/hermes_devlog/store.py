"""Locked, revision-checked local persistence."""

import fcntl
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
    identifier,
    reject_secrets,
)


class StateStore:
    """Persist one coordinator goal below an isolated Hermes home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = root / "state.json"
        self.config_path = root / "config.json"
        self.activity_path = root / "activity.jsonl"
        self.pending_path = root / ".pending.json"
        self.lock_path = root / ".lock"

    @classmethod
    def from_goal(cls, goal_id: str, home: str | Path | None = None) -> "StateStore":
        """Resolve a validated goal path from HERMES_HOME."""
        identifier(goal_id, "goal_id")
        base = Path(home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        return cls(base / "dev-log" / goal_id)

    def read(self) -> dict:
        """Read and validate the supported state version."""
        with self.locked():
            return self._read_unlocked()

    def _read_unlocked(self) -> dict:
        """Read state while the caller holds the per-goal lock."""
        self._recover_pending()
        try:
            state = json.loads(self.state_path.read_text())
        except FileNotFoundError as exc:
            raise CoordinatorError("not_found", "goal state does not exist") from exc
        except json.JSONDecodeError as exc:
            raise CoordinatorError(
                "invalid_state", "goal state is not valid JSON"
            ) from exc
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise CoordinatorError(
                "unsupported_version", "state schema version is unsupported"
            )
        reject_secrets(state)
        validated = validate_state(state)
        self._validate_activity(validated["revision"])
        return validated

    def read_config(self) -> dict:
        """Read and validate the immutable activation configuration."""
        try:
            config = json.loads(self.config_path.read_text())
        except FileNotFoundError as exc:
            raise CoordinatorError("not_found", "goal config does not exist") from exc
        except json.JSONDecodeError as exc:
            raise CoordinatorError(
                "invalid_state", "goal config is not valid JSON"
            ) from exc
        if not isinstance(config, dict) or config.get("schema_version") != 1:
            raise CoordinatorError(
                "invalid_state", "goal config version is unsupported"
            )
        config = {
            key: value for key, value in config.items() if key != "schema_version"
        }
        try:
            return activation_payload(config)
        except CoordinatorError as exc:
            raise CoordinatorError("invalid_state", "goal config is invalid") from exc

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

    def create(self, config: dict, state: dict) -> dict:
        """Atomically create a goal, refusing accidental overwrite."""
        with self.locked():
            if self.state_path.exists() or self.config_path.exists():
                raise CoordinatorError("already_exists", "goal already exists")
            activity_size = (
                self.activity_path.stat().st_size if self.activity_path.exists() else 0
            )
            try:
                self._atomic_json(
                    self.pending_path,
                    self._activity_record("activate", 1),
                )
                self._atomic_json(self.config_path, config)
                self._atomic_json(self.state_path, state)
                self._activity("activate", 1)
                self.pending_path.unlink(missing_ok=True)
            except Exception:
                for path in (self.config_path, self.state_path):
                    path.unlink(missing_ok=True)
                    path.with_name(f".{path.name}.tmp-{os.getpid()}").unlink(
                        missing_ok=True
                    )
                if self.activity_path.exists():
                    with self.activity_path.open("r+") as handle:
                        handle.truncate(activity_size)
                    if activity_size == 0:
                        self.activity_path.unlink(missing_ok=True)
                self.pending_path.unlink(missing_ok=True)
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
    ) -> dict:
        """Apply one revision-checked atomic state mutation."""
        expected = expected_revision(revision)
        with self.locked():
            state = self._read_unlocked()
            if state["revision"] != expected:
                raise CoordinatorError(
                    "revision_conflict",
                    "expected revision does not match current state",
                    expected=expected,
                    actual=state["revision"],
                )
            updated = change(json.loads(json.dumps(state)))
            updated["revision"] = expected + 1
            validate_state(updated)
            state_bytes = self.state_path.read_bytes()
            activity_bytes = self.activity_path.read_bytes()
            try:
                self._atomic_json(
                    self.pending_path,
                    self._activity_record(
                        operation, updated["revision"], actor, verified
                    ),
                )
                self._atomic_json(self.state_path, updated)
                self._activity(operation, updated["revision"], actor, verified)
                self.pending_path.unlink(missing_ok=True)
            except Exception:
                self.state_path.write_bytes(state_bytes)
                self.activity_path.write_bytes(activity_bytes)
                self.pending_path.unlink(missing_ok=True)
                raise
        return updated

    def set_next_action(self, action: str, expected_revision: int) -> dict:
        """Persist a scheduler checkpoint with optimistic concurrency."""

        def change(state: dict) -> dict:
            state["next_action"] = action
            return state

        return self.mutate(expected_revision, "schedule", change)

    def _atomic_json(self, path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        )
        temporary.replace(path)

    def _activity(
        self,
        operation: str,
        revision: int,
        actor: str = "hermes",
        verified: bool = True,
    ) -> None:
        self._append_activity(
            self._activity_record(operation, revision, actor, verified)
        )

    def _activity_record(
        self,
        operation: str,
        revision: int,
        actor: str = "hermes",
        verified: bool = True,
    ) -> dict:
        """Build one validated activity record for journaling or append."""
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "operation": operation,
            "revision": revision,
            "verified": verified,
        }
        if (
            not isinstance(record["timestamp"], str)
            or not isinstance(actor, str)
            or not actor
            or not isinstance(operation, str)
            or not operation
            or not isinstance(revision, int)
            or not isinstance(verified, bool)
        ):
            raise CoordinatorError("invalid_activity", "activity record is invalid")
        return record

    def _append_activity(self, record: dict) -> None:
        with self.activity_path.open("a") as handle:
            handle.write(json.dumps(record, allow_nan=False, sort_keys=True) + "\n")

    def _recover_pending(self) -> None:
        """Finish an interrupted state/activity commit before reading state."""
        if not self.pending_path.exists():
            return
        try:
            pending = json.loads(self.pending_path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoordinatorError(
                "invalid_state", "pending activity record cannot be read"
            ) from exc
        if not isinstance(pending, dict):
            raise CoordinatorError(
                "invalid_state", "pending activity record is invalid"
            )
        self._validate_activity_record(pending, "pending activity record")
        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoordinatorError(
                "invalid_state", "pending state commit cannot be inspected"
            ) from exc
        try:
            lines = self.activity_path.read_text().splitlines()
        except FileNotFoundError:
            lines = []
        except (OSError, UnicodeDecodeError) as exc:
            raise CoordinatorError(
                "invalid_state", "pending activity ledger cannot be inspected"
            ) from exc
        revision = state.get("revision") if isinstance(state, dict) else None
        if revision == pending["revision"] and len(lines) == revision - 1:
            self._append_activity(pending)
        elif revision == pending["revision"] - 1 and len(lines) == revision:
            self.pending_path.unlink()
            return
        elif revision != pending["revision"] or len(lines) != revision:
            raise CoordinatorError(
                "invalid_state", "pending state commit is inconsistent"
            )
        self.pending_path.unlink()

    def _validate_activity(self, state_revision: int) -> None:
        """Validate the append-only activity ledger against state revision."""
        try:
            lines = self.activity_path.read_text().splitlines()
        except (FileNotFoundError, OSError, UnicodeDecodeError) as exc:
            raise CoordinatorError(
                "invalid_state", "activity ledger cannot be read"
            ) from exc
        if len(lines) != state_revision:
            raise CoordinatorError(
                "invalid_state", "activity ledger revision sequence is incomplete"
            )
        fields = {"timestamp", "actor", "operation", "revision", "verified"}
        for expected, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CoordinatorError(
                    "invalid_state", "activity ledger contains invalid JSON"
                ) from exc
            if not isinstance(record, dict) or set(record) != fields:
                raise CoordinatorError(
                    "invalid_state", "activity ledger record is invalid"
                )
            self._validate_activity_record(record, "activity ledger record", expected)

    def _validate_activity_record(
        self, record: object, label: str, expected_revision: int | None = None
    ) -> None:
        if not isinstance(record, dict) or set(record) != {
            "timestamp",
            "actor",
            "operation",
            "revision",
            "verified",
        }:
            raise CoordinatorError("invalid_state", f"{label} is invalid")
        if (
            not isinstance(record["timestamp"], str)
            or not record["timestamp"]
            or not isinstance(record["actor"], str)
            or not record["actor"]
            or not isinstance(record["operation"], str)
            or not record["operation"]
            or not isinstance(record["revision"], int)
            or isinstance(record["revision"], bool)
            or not isinstance(record["verified"], bool)
            or (
                expected_revision is not None
                and record["revision"] != expected_revision
            )
        ):
            raise CoordinatorError("invalid_state", f"{label} is invalid")
