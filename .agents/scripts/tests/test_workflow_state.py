"""Behavior tests for per-issue workflow state."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import workflow_state


ISSUE = "Owner/Repo#42"
INIT = (
    "init",
    ISSUE,
    "--title",
    "Ship workflow state",
    "--url",
    "https://github.com/Owner/Repo/issues/42",
    "--objective",
    "Deliver resumable issue workflows",
    "--format",
    "json",
)


def run(root: Path, *args: str) -> tuple[int, str, str]:
    """Run the CLI against an isolated repository-local root."""
    output: list[str] = []
    errors: list[str] = []
    code = workflow_state.main(
        list(args), root=root, output=output.append, error=errors.append
    )
    return code, "\n".join(output), "\n".join(errors)


def initialized(root: Path) -> dict:
    """Create and return canonical state."""
    code, output, error = run(root, *INIT)
    assert (code, error) == (0, "")
    return json.loads(output)


def advance(root: Path, phase: str) -> None:
    """Advance one phase and require success."""
    if phase == "goal_delivered":
        assert (
            run(
                root,
                "set-review",
                ISSUE,
                "reviews/REVIEW.md",
                "--state",
                "CLEAN",
            )[0]
            == 0
        )
    extra = ("--status", "goal_delivered") if phase == "goal_delivered" else ()
    assert run(root, "transition", ISSUE, phase, *extra)[0] == 0


def test_init_show_and_clear_canonical_state(tmp_path):
    state = initialized(tmp_path)

    assert state.keys() == {
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
    assert state | {"created_at": "TIME", "updated_at": "TIME"} == {
        "schema_version": 4,
        "repository": "Owner/Repo",
        "issue": {
            "number": 42,
            "url": "https://github.com/Owner/Repo/issues/42",
            "title": "Ship workflow state",
        },
        "objective": "Deliver resumable issue workflows",
        "phase": "issue",
        "status": "active",
        "branch": {"name": None, "base": None},
        "artifacts": {
            "directory": None,
            "spec": None,
            "design": None,
            "plan": None,
            "task": None,
            "branch_breakdown": None,
        },
        "specs": None,
        "prs": [],
        "review": None,
        "pending_action": None,
        "environment_retry": {"fingerprint": None, "consecutive_count": 0},
        "created_at": "TIME",
        "updated_at": "TIME",
    }
    assert state["created_at"] == state["updated_at"]
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    assert (
        path.read_text(encoding="utf-8")
        == json.dumps(state, indent=2, sort_keys=True) + "\n"
    )
    assert run(tmp_path, "show", "owner/repo#42", "--format", "json")[1]
    assert run(tmp_path, "clear", "OWNER/REPO#42")[0] == 0
    assert not path.exists()


def test_clear_rejects_state_file_symlink_escape(tmp_path):
    outside = tmp_path.with_name(f"{tmp_path.name}-outside.json")
    try:
        outside.write_text("keep", encoding="utf-8")
        path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
        path.parent.mkdir(parents=True)
        path.symlink_to(outside)

        code, _, error = run(tmp_path, "clear", ISSUE)

        assert code == 1
        assert "escapes" in error
        assert outside.read_text(encoding="utf-8") == "keep"
        assert path.is_symlink()
    finally:
        outside.unlink(missing_ok=True)


def test_clear_rejects_state_parent_symlink_escape(tmp_path):
    outside = tmp_path.with_name(f"{tmp_path.name}-outside")
    try:
        outside.mkdir()
        target = outside / "owner_repo_42.json"
        target.write_text("keep", encoding="utf-8")
        parent = tmp_path / ".agents/local/state"
        parent.mkdir(parents=True)
        (parent / "goals").symlink_to(outside, target_is_directory=True)

        code, _, error = run(tmp_path, "clear", ISSUE)

        assert code == 1
        assert "escapes" in error
        assert target.read_text(encoding="utf-8") == "keep"
    finally:
        if outside.exists():
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()


def test_init_requires_metadata_and_does_not_replace_existing_state(tmp_path):
    assert run(tmp_path, "init", ISSUE)[0] == 2
    original = initialized(tmp_path)

    code, output, _ = run(
        tmp_path,
        "init",
        ISSUE,
        "--title",
        "Different",
        "--url",
        "https://github.com/Owner/Repo/issues/42",
        "--objective",
        "Different",
        "--format",
        "json",
    )

    assert code == 0
    assert json.loads(output) == original


def test_show_missing_state_does_not_create_directories(tmp_path):
    code, _, error = run(tmp_path, "show", "owner/repo#1")
    assert code == 1
    assert "not found" in error.lower()
    assert not (tmp_path / ".agents").exists()


def test_resolve_active_returns_the_only_nonterminal_state(tmp_path):
    expected = initialized(tmp_path)

    code, output, error = run(tmp_path, "resolve-active", "--format", "json")

    assert (code, error) == (0, "")
    assert json.loads(output) == expected


def test_resolve_active_migrates_legacy_issue_state(tmp_path):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["schema_version"] = 2
    state.pop("environment_retry")
    path.write_text(json.dumps(state), encoding="utf-8")

    code, output, error = run(tmp_path, "resolve-active", "--format", "json")

    assert (code, error) == (0, "")
    resolved = json.loads(output)
    assert resolved["schema_version"] == 4
    assert resolved["environment_retry"] == {
        "fingerprint": None,
        "consecutive_count": 0,
    }


def test_existing_v3_state_without_specs_remains_resumable(tmp_path):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["schema_version"] = 3
    state.pop("specs")
    path.write_text(json.dumps(state), encoding="utf-8")

    code, output, error = run(tmp_path, "show", ISSUE, "--format", "json")

    assert (code, error) == (0, "")
    assert json.loads(output)["schema_version"] == 4
    assert json.loads(output)["specs"] is None
    code, output, error = run(tmp_path, "resolve-active", "--format", "json")
    assert (code, error) == (0, "")
    assert json.loads(output)["schema_version"] == 4
    assert json.loads(output)["specs"] is None


def test_resolve_active_fails_for_zero_or_multiple_states(tmp_path):
    assert run(tmp_path, "resolve-active")[0] == 1
    initialized(tmp_path)
    second = list(INIT)
    second[1] = "Owner/Repo#43"
    assert run(tmp_path, *second)[0] == 0

    code, _, error = run(tmp_path, "resolve-active")

    assert code == 1
    assert "multiple" in error.lower()


@pytest.mark.parametrize("status", ["active", "paused", "needs_user", "blocked"])
def test_resolve_active_includes_each_resumable_status(tmp_path, status):
    initialized(tmp_path)
    assert run(tmp_path, "transition", ISSUE, "--status", status)[0] == 0
    assert run(tmp_path, "resolve-active")[0] == 0


def test_resolve_active_ignores_terminal_states(tmp_path):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:]:
        advance(tmp_path, phase)
    assert run(tmp_path, "transition", ISSUE, "--status", "complete")[0] == 0

    code, _, error = run(tmp_path, "resolve-active")

    assert code == 1
    assert "no active" in error.lower()


def test_resolve_active_reports_malformed_state(tmp_path):
    directory = tmp_path / ".agents/local/state/goals"
    directory.mkdir(parents=True)
    (directory / "bad.json").write_text("[]", encoding="utf-8")

    code, _, error = run(tmp_path, "resolve-active")

    assert code == 1
    assert "unknown or missing fields" in error


@pytest.mark.parametrize(
    "issue",
    ["owner/repo", "owner/repo#0", "owner/repo#x", "../repo#1", "owner/a/b#1"],
)
def test_rejects_malformed_issue_keys(tmp_path, issue):
    assert run(tmp_path, "show", issue)[0] == 2
    assert not (tmp_path / ".agents").exists()


def test_transition_enforces_graph_and_updates_status_action_and_time(tmp_path):
    state = initialized(tmp_path)
    code, output, _ = run(
        tmp_path,
        "transition",
        ISSUE,
        "branched",
        "--status",
        "needs_user",
        "--pending-action",
        "approve plan",
        "--format",
        "json",
    )
    assert code == 0
    changed = json.loads(output)
    assert changed["phase"] == "branched"
    assert changed["status"] == "needs_user"
    assert changed["pending_action"] == "approve plan"
    assert changed["created_at"] == state["created_at"]
    assert changed["updated_at"] >= state["updated_at"]

    assert run(tmp_path, "transition", ISSUE, "reviewing")[0] == 1
    assert run(tmp_path, "transition", ISSUE, "branched", "--status", "unknown")[0] == 2


def test_transition_can_clear_pending_action_and_rejects_invalid_phase_status(tmp_path):
    initialized(tmp_path)
    assert (
        run(
            tmp_path,
            "transition",
            ISSUE,
            "--status",
            "needs_user",
            "--pending-action",
            "approve plan",
        )[0]
        == 0
    )
    code, output, _ = run(
        tmp_path,
        "transition",
        ISSUE,
        "--status",
        "active",
        "--clear-pending-action",
        "--format",
        "json",
    )
    assert code == 0
    assert json.loads(output)["pending_action"] is None
    assert (
        run(
            tmp_path,
            "transition",
            ISSUE,
            "--pending-action",
            "x",
            "--clear-pending-action",
        )[0]
        == 2
    )
    assert run(tmp_path, "transition", ISSUE, "--status", "goal_delivered")[0] == 1


def test_environment_retry_records_persists_and_replaces_fingerprint(tmp_path):
    initialized(tmp_path)

    for fingerprint in ("network unavailable", "network unavailable", "DNS unavailable"):
        assert (
            run(
                tmp_path,
                "record-environment-failure",
                ISSUE,
                "--fingerprint",
                fingerprint,
                "--resume-action",
                "retry when the environment is available",
            )[0]
            == 0
        )

    state = json.loads(run(tmp_path, "show", ISSUE, "--format", "json")[1])
    assert state["environment_retry"] == {
        "fingerprint": "DNS unavailable",
        "consecutive_count": 1,
    }


def test_environment_retry_blocks_on_fifth_identical_failure(tmp_path):
    initialized(tmp_path)

    for _ in range(4):
        assert (
            run(
                tmp_path,
                "record-environment-failure",
                ISSUE,
                "--fingerprint",
                "network unavailable",
                "--resume-action",
                "retry the implementation phase",
            )[0]
            == 0
        )
    code, output, _ = run(
        tmp_path,
        "record-environment-failure",
        ISSUE,
        "--fingerprint",
        "network unavailable",
        "--resume-action",
        "retry the implementation phase",
        "--format",
        "json",
    )

    assert code == 0
    state = json.loads(output)
    assert state["status"] == "blocked"
    assert state["environment_retry"] == {
        "fingerprint": "network unavailable",
        "consecutive_count": 5,
    }
    assert state["pending_action"] == (
        "Environment failure after 5 consecutive identical attempts "
        "(network unavailable): retry the implementation phase"
    )


def test_environment_retry_resets_after_meaningful_progress(tmp_path):
    initialized(tmp_path)
    assert (
        run(
            tmp_path,
            "record-environment-failure",
            ISSUE,
            "--fingerprint",
            "network unavailable",
            "--resume-action",
            "retry the implementation phase",
        )[0]
        == 0
    )

    code, output, error = run(
        tmp_path, "reset-environment-retry", ISSUE, "--format", "json"
    )

    assert (code, error) == (0, "")
    assert json.loads(output)["environment_retry"] == {
        "fingerprint": None,
        "consecutive_count": 0,
    }


def test_environment_retry_rejects_malformed_state_and_migrates_legacy_issue(tmp_path):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["schema_version"] = 2
    state.pop("environment_retry")
    path.write_text(json.dumps(state), encoding="utf-8")

    assert run(tmp_path, "show", ISSUE)[0] == 0
    assert run(tmp_path, "reset-environment-retry", ISSUE)[0] == 0
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 4
    assert migrated["environment_retry"] == {"fingerprint": None, "consecutive_count": 0}

    migrated["environment_retry"] = {"fingerprint": None, "consecutive_count": 1}
    path.write_text(json.dumps(migrated), encoding="utf-8")
    assert run(tmp_path, "show", ISSUE)[0] == 1


def test_metadata_commands_store_structured_values(tmp_path):
    initialized(tmp_path)
    assert run(tmp_path, "set-branch", ISSUE, "feature/state", "--base", "main")[0] == 0
    advance(tmp_path, "branched")
    assert (
        run(
            tmp_path,
            "set-artifacts",
            ISSUE,
            "--directory",
            ".agents/local/state/artifacts/42",
            "--spec",
            ".agents/local/state/artifacts/42/spec.md",
            "--design",
            ".agents/local/state/artifacts/42/design.md",
            "--plan",
            ".agents/local/state/artifacts/42/implementation-plan.md",
            "--task",
            ".agents/local/state/artifacts/42/task.md",
            "--branch-breakdown",
            ".agents/local/state/artifacts/42/branches.json",
        )[0]
        == 0
    )
    advance(tmp_path, "planned")
    advance(tmp_path, "implementing")
    advance(tmp_path, "implemented")
    advance(tmp_path, "awaiting_commit")
    advance(tmp_path, "awaiting_push")
    assert (
        run(
            tmp_path,
            "set-pr",
            ISSUE,
            "123",
            "--url",
            "https://github.com/Owner/Repo/pull/123",
            "--head",
            "feature/state",
            "--base",
            "main",
        )[0]
        == 0
    )
    advance(tmp_path, "pr_open")
    assert (
        run(
            tmp_path,
            "set-review",
            ISSUE,
            "reviews/REVIEW.md",
            "--state",
            "ARCHIVED",
            "--archive",
            "reviews/archive/REVIEW.md",
        )[0]
        == 0
    )

    state = json.loads(run(tmp_path, "show", ISSUE, "--format", "json")[1])
    assert state["branch"] == {"name": "feature/state", "base": "main"}
    assert state["artifacts"]["branch_breakdown"].endswith("branches.json")
    assert state["prs"] == [
        {
            "number": 123,
            "url": "https://github.com/Owner/Repo/pull/123",
            "head": "feature/state",
            "base": "main",
        }
    ]
    assert state["review"] == {
        "report": "reviews/REVIEW.md",
        "state": "ARCHIVED",
        "archive": "reviews/archive/REVIEW.md",
    }


def test_set_specs_stores_complete_same_issue_remote_references(tmp_path):
    initialized(tmp_path)
    advance(tmp_path, "branched")
    base = "https://github.com/Owner/Repo/issues/77"

    code, output, error = run(
        tmp_path,
        "set-specs",
        ISSUE,
        "--number",
        "77",
        "--url",
        base,
        "--index-url",
        base,
        "--revision",
        "1",
        "--spec-url",
        f"{base}#issuecomment-1",
        "--design-url",
        f"{base}#issuecomment-2",
        "--plan-url",
        f"{base}#issuecomment-3",
        "--task-url",
        f"{base}#issuecomment-4",
        "--format",
        "json",
    )

    assert (code, error) == (0, "")
    assert json.loads(output)["specs"] == {
        "number": 77,
        "url": base,
        "index_url": base,
        "revision": 1,
        "documents": {
            "spec": f"{base}#issuecomment-1",
            "design": f"{base}#issuecomment-2",
            "plan": f"{base}#issuecomment-3",
            "task": f"{base}#issuecomment-4",
        },
    }


def test_set_specs_rejects_foreign_or_incomplete_references(tmp_path):
    initialized(tmp_path)
    advance(tmp_path, "branched")

    code, _, error = run(
        tmp_path,
        "set-specs",
        ISSUE,
        "--number",
        "77",
        "--url",
        "https://github.com/Other/Repo/issues/77",
        "--index-url",
        "https://github.com/Other/Repo/issues/77",
        "--revision",
        "1",
        "--spec-url",
        "https://github.com/Other/Repo/issues/77#issuecomment-1",
        "--design-url",
        "https://github.com/Other/Repo/issues/77#issuecomment-2",
        "--plan-url",
        "https://github.com/Other/Repo/issues/77#issuecomment-3",
        "--task-url",
        "https://github.com/Other/Repo/issues/77#issuecomment-4",
    )

    assert code == 1
    assert "specs" in error


def test_set_pr_keeps_ordered_per_branch_collection_and_updates_in_place(tmp_path):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:7]:
        advance(tmp_path, phase)
    for number, head, base in (
        (10, "stack/one", "main"),
        (11, "stack/two", "stack/one"),
    ):
        assert (
            run(
                tmp_path,
                "set-pr",
                ISSUE,
                str(number),
                "--url",
                f"https://github.com/Owner/Repo/pull/{number}",
                "--head",
                head,
                "--base",
                base,
            )[0]
            == 0
        )
    assert (
        run(
            tmp_path,
            "set-pr",
            ISSUE,
            "10",
            "--url",
            "https://github.com/Owner/Repo/pull/10",
            "--head",
            "stack/one-updated",
            "--base",
            "main",
        )[0]
        == 0
    )

    state = json.loads(run(tmp_path, "show", ISSUE, "--format", "json")[1])
    assert [pr["head"] for pr in state["prs"]] == ["stack/one-updated", "stack/two"]
    assert [pr["number"] for pr in state["prs"]] == [10, 11]


def test_set_pr_refreshes_head_while_reviewing(tmp_path):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:7]:
        advance(tmp_path, phase)
    assert (
        run(
            tmp_path,
            "set-pr",
            ISSUE,
            "10",
            "--url",
            "https://github.com/Owner/Repo/pull/10",
            "--head",
            "feature/state",
            "--base",
            "main",
        )[0]
        == 0
    )
    advance(tmp_path, "pr_open")
    advance(tmp_path, "reviewing")

    assert (
        run(
            tmp_path,
            "set-pr",
            ISSUE,
            "10",
            "--url",
            "https://github.com/Owner/Repo/pull/10",
            "--head",
            "feature/state-after-push",
            "--base",
            "main",
        )[0]
        == 0
    )

    state = json.loads(run(tmp_path, "show", ISSUE, "--format", "json")[1])
    assert state["prs"] == [
        {
            "number": 10,
            "url": "https://github.com/Owner/Repo/pull/10",
            "head": "feature/state-after-push",
            "base": "main",
        }
    ]


@pytest.mark.parametrize("field", ["number", "url"])
def test_set_pr_rejects_identity_collision_with_another_head(tmp_path, field):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:7]:
        advance(tmp_path, phase)
    first = ("10", "https://github.com/Owner/Repo/pull/10", "stack/one")
    second = ("11", "https://github.com/Owner/Repo/pull/11", "stack/two")
    for number, url, head in (first, second):
        assert (
            run(
                tmp_path,
                "set-pr",
                ISSUE,
                number,
                "--url",
                url,
                "--head",
                head,
                "--base",
                "main",
            )[0]
            == 0
        )

    number, url, _ = second
    if field == "number":
        number = first[0]
    else:
        url = first[1]
    assert (
        run(
            tmp_path,
            "set-pr",
            ISSUE,
            number,
            "--url",
            url,
            "--head",
            "stack/two",
            "--base",
            "main",
        )[0]
        == 1
    )


def test_show_rejects_duplicate_pr_number_and_url(tmp_path):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["prs"] = [
        {"number": 1, "url": "https://example.test/1", "head": "one", "base": "main"},
        {"number": 1, "url": "https://example.test/1", "head": "two", "base": "main"},
    ]
    path.write_text(json.dumps(state), encoding="utf-8")

    assert run(tmp_path, "show", ISSUE)[0] == 1


@pytest.mark.parametrize("state", ["open", "ACTIVE", "clean", "UNKNOWN"])
def test_set_review_rejects_unknown_state(tmp_path, state):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:8]:
        advance(tmp_path, phase)

    assert run(tmp_path, "set-review", ISSUE, "reviews/R.md", "--state", state)[0] == 1


def test_goal_delivered_requires_clean_or_archived_review_evidence(tmp_path):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:9]:
        advance(tmp_path, phase)

    assert (
        run(
            tmp_path,
            "transition",
            ISSUE,
            "goal_delivered",
            "--status",
            "goal_delivered",
        )[0]
        == 1
    )
    assert (
        run(
            tmp_path,
            "set-review",
            ISSUE,
            "reviews/R.md",
            "--state",
            "CLEAN",
        )[0]
        == 0
    )
    assert (
        run(
            tmp_path,
            "transition",
            ISSUE,
            "goal_delivered",
            "--status",
            "goal_delivered",
        )[0]
        == 0
    )


def test_archived_review_requires_archive_path_before_delivery(tmp_path):
    initialized(tmp_path)
    for phase in workflow_state.PHASES[1:9]:
        advance(tmp_path, phase)

    assert (
        run(
            tmp_path,
            "set-review",
            ISSUE,
            "reviews/R.md",
            "--state",
            "ARCHIVED",
        )[0]
        == 1
    )
    assert (
        run(
            tmp_path,
            "set-review",
            ISSUE,
            "reviews/R.md",
            "--state",
            "ARCHIVED",
            "--archive",
            "reviews/archive/R.md",
        )[0]
        == 0
    )


def test_paths_and_stored_schema_are_strict(tmp_path):
    initialized(tmp_path)
    advance(tmp_path, "branched")
    assert run(tmp_path, "set-artifacts", ISSUE, "--plan", "../plan.md")[0] == 1
    assert run(tmp_path, "set-artifacts", ISSUE, "--unknown", "x")[0] == 2

    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["extra"] = True
    path.write_text(json.dumps(state), encoding="utf-8")
    assert run(tmp_path, "show", ISSUE)[0] == 1


@pytest.mark.parametrize(
    ("action", "args", "allowed"),
    [
        ("set-branch", ("feature/state", "--base", "main"), {"issue", "branched"}),
        ("set-artifacts", ("--plan", "plan.md"), {"branched", "planned"}),
        (
            "set-pr",
            (
                "1",
                "--url",
                "https://example.test/1",
                "--head",
                "feature/state",
                "--base",
                "main",
            ),
            {"awaiting_push", "pr_open", "reviewing"},
        ),
        (
            "set-review",
            ("reviews/R.md", "--state", "CLEAN"),
            {"pr_open", "reviewing", "goal_delivered"},
        ),
    ],
)
def test_metadata_commands_enforce_phase_guards_and_allow_resume(
    tmp_path, action, args, allowed
):
    initialized(tmp_path)
    for phase in workflow_state.PHASES:
        code = run(tmp_path, action, ISSUE, *args)[0]
        assert (code == 0) == (phase in allowed), (action, phase)
        if phase != workflow_state.PHASES[-1]:
            advance(
                tmp_path, workflow_state.PHASES[workflow_state.PHASES.index(phase) + 1]
            )


def test_show_rejects_wrong_nested_types_without_rewriting(tmp_path):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["issue"]["number"] = True
    content = json.dumps(state)
    path.write_text(content, encoding="utf-8")

    assert run(tmp_path, "show", ISSUE)[0] == 1
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize(
    ("created_at", "updated_at", "valid"),
    [
        ("2026-01-01T01:00:00+01:00", "2026-01-01T00:30:00Z", True),
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.1Z", True),
    ],
)
def test_timestamp_order_uses_normalized_instants_and_preserves_strings(
    tmp_path, created_at, updated_at, valid
):
    initialized(tmp_path)
    path = tmp_path / ".agents/local/state/goals/owner_repo_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["created_at"] = created_at
    state["updated_at"] = updated_at
    path.write_text(json.dumps(state), encoding="utf-8")

    code, output, _ = run(tmp_path, "show", ISSUE, "--format", "json")

    assert (code == 0) is valid
    if valid:
        shown = json.loads(output)
        assert shown["created_at"] == created_at
        assert shown["updated_at"] == updated_at


def test_human_output_remains_easy_to_consume(tmp_path):
    _, output, _ = run(tmp_path, *INIT[:-2])
    assert "Owner/Repo#42" in output
    assert "issue" in output
    assert "active" in output


def test_direct_pr_plan_rejects_a_changed_head(tmp_path):
    pr = "Owner/Repo!42"
    code, _, error = run(
        tmp_path,
        "init-pr",
        pr,
        "--title",
        "Resume direct PR",
        "--url",
        "https://github.com/Owner/Repo/pull/42",
        "--head",
        "a" * 40,
    )
    assert (code, error) == (0, "")
    assert run(
        tmp_path,
        "set-plan-head",
        pr,
        "--head",
        "a" * 40,
    )[0] == 0
    assert run(tmp_path, "validate-plan-head", pr, "--head", "a" * 40)[0] == 0

    code, _, error = run(tmp_path, "validate-plan-head", pr, "--head", "b" * 40)

    assert code == 1
    assert "stale" in error


def test_existing_pr_state_without_specs_remains_resumable(tmp_path):
    pr = "Owner/Repo!42"
    assert (
        run(
            tmp_path,
            "init-pr",
            pr,
            "--title",
            "Resume direct PR",
            "--url",
            "https://github.com/Owner/Repo/pull/42",
            "--head",
            "a" * 40,
        )[0]
        == 0
    )
    assert run(tmp_path, "set-plan-head", pr, "--head", "a" * 40)[0] == 0
    path = tmp_path / ".agents/local/state/goals/owner_repo_pr_42.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("specs")
    path.write_text(json.dumps(state), encoding="utf-8")

    code, output, error = run(
        tmp_path, "validate-plan-head", pr, "--head", "a" * 40, "--format", "json"
    )

    assert (code, error) == (0, "")
    assert json.loads(output)["specs"] is None
    code, output, error = run(tmp_path, "resolve-active", "--format", "json")
    assert (code, error) == (0, "")
    assert json.loads(output)["specs"] is None
