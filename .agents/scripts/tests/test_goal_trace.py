"""Behavior tests for local per-goal trace records."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import goal_trace


ISSUE = "Owner/Repo#42"
KEY = "owner_repo_42"
FILES = ("goals.config.json", "goals.logs.json", "goals.audit.json")


def run(root: Path, *args: str) -> tuple[int, str, str]:
    """Run the CLI against an isolated repository-local root."""
    output: list[str] = []
    errors: list[str] = []
    code = goal_trace.main(list(args), root=root, output=output.append, error=errors.append)
    return code, "\n".join(output), "\n".join(errors)


def trace_dir(root: Path) -> Path:
    """Return the canonical trace directory."""
    return root / ".agents/local/state/goals" / KEY


def initialized(root: Path) -> Path:
    """Initialize and return a valid trace directory."""
    template = Path(goal_trace.__file__).parent.parent / "templates"
    destination = root / ".agents/templates"
    destination.mkdir(parents=True)
    (destination / "goals.config.default.json").write_bytes(
        (template / "goals.config.default.json").read_bytes()
    )
    code, _, error = run(root, "init", ISSUE, "--auto", "--commit")
    assert (code, error) == (0, "")
    return trace_dir(root)


def snapshots(directory: Path) -> dict[str, bytes]:
    """Capture trace file contents exactly."""
    return {name: (directory / name).read_bytes() for name in FILES}


def test_init_creates_the_exact_issue_keyed_files_from_the_default(tmp_path):
    directory = initialized(tmp_path)

    assert {path.name for path in directory.iterdir()} == set(FILES)
    config = json.loads((directory / "goals.config.json").read_text(encoding="utf-8"))
    assert config["schema_version"] == 1
    assert config["goal"] == "owner/repo#42"
    assert config["permissions"] == {
        "auto": True,
        "commit": True,
        "push": False,
        "pr_create": False,
        "pr_ready": False,
        "merge": False,
        "administrator_merge": False,
    }
    assert isinstance(config["recorded_at"], str)
    assert json.loads((directory / "goals.logs.json").read_text(encoding="utf-8")) == []
    assert json.loads((directory / "goals.audit.json").read_text(encoding="utf-8")) == []


def test_init_updates_permission_metadata_without_replacing_trace_records(tmp_path):
    directory = initialized(tmp_path)
    before = snapshots(directory)

    code, _, error = run(
        tmp_path, "init", ISSUE, "--auto", "--commit", "--push", "--merge"
    )

    assert (code, error) == (0, "")
    config = json.loads((directory / "goals.config.json").read_text(encoding="utf-8"))
    assert config["permissions"] == {
        "auto": True,
        "commit": True,
        "push": True,
        "pr_create": False,
        "pr_ready": False,
        "merge": True,
        "administrator_merge": False,
    }
    assert snapshots(directory)["goals.logs.json"] == before["goals.logs.json"]
    assert snapshots(directory)["goals.audit.json"] == before["goals.audit.json"]


def test_validate_is_read_only_and_requires_all_three_files(tmp_path):
    directory = initialized(tmp_path)
    before = snapshots(directory)

    code, output, error = run(tmp_path, "validate", ISSUE)

    assert (code, error) == (0, "")
    assert json.loads(output)["goal"] == "owner/repo#42"
    assert snapshots(directory) == before

    (directory / "goals.audit.json").unlink()
    code, _, error = run(tmp_path, "validate", ISSUE)
    assert code == 1
    assert "goals.audit.json" in error


def test_validate_missing_trace_does_not_create_directories(tmp_path):
    code, _, error = run(tmp_path, "validate", ISSUE)

    assert code == 1
    assert "goals.config.json" in error
    assert not (tmp_path / ".agents").exists()


@pytest.mark.parametrize("filename", FILES)
def test_validate_rejects_each_malformed_file_without_writing(tmp_path, filename):
    directory = initialized(tmp_path)
    target = directory / filename
    target.write_text("{", encoding="utf-8")
    before = snapshots(directory)

    code, _, error = run(tmp_path, "validate", ISSUE)

    assert code == 1
    assert filename in error
    assert snapshots(directory) == before


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("goals.config.json", {"schema_version": 1}),
        ("goals.logs.json", [{"schema_version": 1}]),
        ("goals.audit.json", [{"schema_version": 1}]),
    ],
)
def test_validate_rejects_each_schema_drift_without_writing(tmp_path, filename, content):
    directory = initialized(tmp_path)
    target = directory / filename
    target.write_text(json.dumps(content), encoding="utf-8")
    before = snapshots(directory)

    code, _, error = run(tmp_path, "validate", ISSUE)

    assert code == 1
    assert filename in error
    assert snapshots(directory) == before


@pytest.mark.parametrize("action", ["append-log", "append-audit"])
def test_append_validates_identity_of_every_companion_before_mutation(tmp_path, action):
    directory = initialized(tmp_path)
    logs = directory / "goals.logs.json"
    logs.write_text(
        json.dumps(
            [
                {
                    "schema_version": 1,
                    "goal": "other/repo#42",
                    "at": "2026-01-01T00:00:00Z",
                    "event": "transition",
                    "phase": "issue",
                    "summary": "Started planning.",
                    "reason": None,
                    "resume_action": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    before = snapshots(directory)
    args = (
        ("--event", "transition", "--phase", "issue", "--summary", "Started planning.")
        if action == "append-log"
        else ("--stage", "plan", "--outcome", "started", "--detail", "Planning began.")
    )

    code, _, error = run(tmp_path, action, ISSUE, *args)

    assert code == 1
    assert "goals.logs.json" in error
    assert snapshots(directory) == before


def test_append_operations_add_only_valid_tail_records_in_order(tmp_path):
    directory = initialized(tmp_path)
    assert run(
        tmp_path,
        "append-log",
        ISSUE,
        "--event",
        "reason",
        "--phase",
        "implementing",
        "--summary",
        "Implementation paused.",
        "--reason",
        "Tests need repair.",
        "--resume-action",
        "Fix the failing test.",
    )[0] == 0
    assert run(
        tmp_path,
        "append-audit",
        ISSUE,
        "--stage",
        "implement",
        "--outcome",
        "succeeded",
        "--detail",
        "Implementation and tests completed.",
    )[0] == 0

    logs = json.loads((directory / "goals.logs.json").read_text(encoding="utf-8"))
    audit = json.loads((directory / "goals.audit.json").read_text(encoding="utf-8"))
    assert logs[0]["goal"] == audit[0]["goal"] == "owner/repo#42"
    assert logs[0]["event"] == "reason"
    assert audit[0]["outcome"] == "succeeded"


@pytest.mark.parametrize(
    ("args", "field"),
    [
        (("--event", "reason", "--phase", "issue", "--summary", "Stopped."), "reason"),
        (
            (
                "--event",
                "transition",
                "--phase",
                "issue",
                "--summary",
                "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
            ),
            "summary",
        ),
        (
            (
                "--stage",
                "plan",
                "--outcome",
                "started",
                "--detail",
                "API_TOKEN=super-secret",
            ),
            "detail",
        ),
    ],
)
def test_append_rejects_invalid_or_token_like_input_without_echoing_it(
    tmp_path, args, field
):
    directory = initialized(tmp_path)
    before = snapshots(directory)
    action = "append-audit" if "--stage" in args else "append-log"

    code, _, error = run(tmp_path, action, ISSUE, *args)

    assert code == 1
    assert field in error
    assert "ghp_" not in error
    assert "super-secret" not in error
    assert snapshots(directory) == before


def test_validate_rejects_trace_file_symlinks(tmp_path):
    directory = initialized(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    target = directory / "goals.logs.json"
    target.unlink()
    target.symlink_to(outside)

    code, _, error = run(tmp_path, "validate", ISSUE)

    assert code == 1
    assert "goals.logs.json" in error
    assert outside.read_text(encoding="utf-8") == "[]"


def test_append_preserves_all_records_when_atomic_replacement_fails(tmp_path, monkeypatch):
    directory = initialized(tmp_path)
    before = snapshots(directory)

    def fail_replace(source, destination):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(goal_trace.os, "replace", fail_replace)
    code, _, error = run(
        tmp_path,
        "append-log",
        ISSUE,
        "--event",
        "transition",
        "--phase",
        "issue",
        "--summary",
        "Started planning.",
    )

    assert code == 1
    assert "replacement failure" in error
    assert snapshots(directory) == before
