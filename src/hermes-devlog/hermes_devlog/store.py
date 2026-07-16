"""Locked, revision-checked local persistence."""

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .errors import CoordinatorError
from .validation import (
    activation_payload,
    expected_revision,
    identifier,
    reject_secrets,
    validate_state,
)


class StateStore:
    """Persist one coordinator goal below an isolated Hermes home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = root / "state.json"
        self.config_path = root / "config.json"
        self.activity_path = root / "activity.jsonl"
        self.lock_path = root / ".lock"

    @classmethod
    def from_goal(cls, goal_id: str, home: str | Path | None = None) -> "StateStore":
        """Resolve a validated goal path from HERMES_HOME."""
        identifier(goal_id, "goal_id")
        base = Path(home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        return cls(base / "dev-log" / goal_id)

    def read(self) -> dict:
        """Read and validate the supported state version."""
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
        return validate_state(state)

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
            self._atomic_json(self.config_path, config)
            self._atomic_json(self.state_path, state)
            self._activity("activate", 1)
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
            state = self.read()
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
            self._atomic_json(self.state_path, updated)
            self._activity(operation, updated["revision"], actor, verified)
        return updated

    def set_next_action(self, action: str) -> dict:
        """Persist a scheduler checkpoint when it differs from the current one."""
        with self.locked():
            state = self.read()
            if state["next_action"] == action:
                return state
            state["next_action"] = action
            state["revision"] += 1
            validate_state(state)
            self._atomic_json(self.state_path, state)
            self._activity("schedule", state["revision"])
            return state

    def _atomic_json(self, path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)

    def _activity(
        self,
        operation: str,
        revision: int,
        actor: str = "hermes",
        verified: bool = True,
    ) -> None:
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
        with self.activity_path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
