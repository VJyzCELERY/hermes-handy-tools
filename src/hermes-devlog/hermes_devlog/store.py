"""Locked, revision-checked local persistence."""

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from .errors import CoordinatorError
from .validation import expected_revision, identifier, reject_secrets


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
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise CoordinatorError(
                "unsupported_version", "state schema version is unsupported"
            )
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
        if set(state) - allowed:
            raise CoordinatorError("unknown_field", "unknown field in state")
        reject_secrets(state)
        return state

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
        self, revision: int, operation: str, change: Callable[[dict], dict]
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
            self._atomic_json(self.state_path, updated)
            self._activity(operation, updated["revision"])
        return updated

    def _atomic_json(self, path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)

    def _activity(self, operation: str, revision: int) -> None:
        record = {"revision": revision, "operation": operation}
        with self.activity_path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
