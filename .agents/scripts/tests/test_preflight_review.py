"""Regression tests for preflight-review.py."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli_common


def load_script():
    path = Path(__file__).parent.parent / "preflight-review.py"
    spec = importlib.util.spec_from_file_location("preflight_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "content",
    [
        "# Review Report: test\n**Branch**: main\n",
        "# Review Report: test\n**Branch**: main\n**Commit Range**: invalid\n",
        "# Review Report: test\n**Commit Range**: aaa...bbb\n",
        "**Branch**: main\n**Commit Range**: aaa...bbb\n",
    ],
)
def test_parse_review_header_rejects_missing_or_malformed_headers(content):
    module = load_script()

    with patch("builtins.open", create=True) as review:
        review.return_value.__enter__.return_value.read.return_value = content

        assert module.parse_review_header("reviews/REVIEW_test.md") is None


def test_autodetect_reports_malformed_review_as_invalid(capsys):
    module = load_script()
    reviews_dir = MagicMock()
    reviews_dir.exists.return_value = True
    reviews_dir.glob.return_value = [Path("reviews/REVIEW_bad.md")]

    def command_output(command):
        if command[:3] == ["git", "branch", "--show-current"]:
            return "feature"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "bbb"
        return ""

    with (
        patch.object(module, "Path", return_value=reviews_dir),
        patch.object(module, "run", side_effect=command_output),
        patch.object(module, "parse_review_header", return_value=None),
    ):
        code = module.implement_preflight_autodetect()

    output = capsys.readouterr().out
    assert code != 0
    assert "REVIEW_bad.md - Invalid" in output
    assert "All local reviews are active" not in output


@pytest.mark.parametrize(
    ("process_kwargs", "diagnostic"),
    [
        ({"side_effect": subprocess.TimeoutExpired(["gh.py"], 30)}, "timed out"),
        (
            {
                "return_value": subprocess.CompletedProcess(
                    ["gh.py"], 1, stdout="", stderr="authentication failed"
                )
            },
            "authentication failed",
        ),
    ],
)
def test_nested_gh_failure_exits_external_without_writing(
    process_kwargs, diagnostic, capsys
):
    module = load_script()

    def command_output(command):
        if command[:3] == ["git", "branch", "--show-current"]:
            return "feature"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "bbb"
        if "pr" in command and "list" in command:
            return '[{"number":42}]'
        return ""

    with (
        patch.object(sys, "argv", ["preflight-review.py", "--implement"]),
        patch.object(module, "run", side_effect=command_output),
        patch.object(cli_common.subprocess, "run", **process_kwargs),
        patch.object(Path, "write_text") as write_text,
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    captured = capsys.readouterr()
    assert exit_info.value.code == 3
    assert diagnostic in (captured.out + captured.err).lower()
    write_text.assert_not_called()


def test_init_review_rejects_unsafe_directory_before_file_activity():
    module = load_script()
    module._commit_base = "aaa"

    with (
        patch.object(module, "run", return_value="bbb"),
        patch.object(Path, "mkdir") as mkdir,
        patch.object(Path, "write_text") as write_text,
        pytest.raises(ValueError, match="escapes the repository root"),
    ):
        module.init_review("REVIEW_test", "../outside")

    mkdir.assert_not_called()
    write_text.assert_not_called()


def test_run_preserves_external_command_failure():
    module = load_script()

    with (
        patch.object(
            cli_common.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["git", "status"], 2, stdout="", stderr="broken"
            ),
        ),
        pytest.raises(module.ExternalCommandError, match="broken"),
    ):
        module.run(["git", "status"])


def test_scope_pr_routes_gh_commands_through_wrapper():
    module = load_script()
    commands = []

    def command_output(command):
        commands.append(command)
        if command == ["git", "branch", "--show-current"]:
            return "feature"
        if "pr" in command and "list" in command:
            return '[{"number":42,"headRefName":"feature","baseRefName":"main","title":"Test"}]'
        if "pr" in command and "diff" in command:
            return "changed.py"
        if command[:2] == ["git", "merge-base"]:
            return "aaa"
        return ""

    with patch.object(module, "run", side_effect=command_output):
        output = module.scope_pr()

    gh_commands = [command for command in commands if "gh.py" in " ".join(command)]
    assert [command[2:5] for command in gh_commands] == [
        ["cmd", "--format", "json"],
        ["cmd", "--format", "raw"],
    ]
    assert all(command[0] != "gh" for command in commands)
    assert "[INFO] PR #42: Test" in output


def test_scope_branch_without_upstream_skips_remote_comparison():
    module = load_script()
    commands = []

    def command_output(command):
        commands.append(command)
        if command == ["git", "branch", "--show-current"]:
            return "feature"
        if command[:3] == ["git", "for-each-ref", "--format=%(upstream:short)"]:
            return ""
        if command[:2] == ["git", "merge-base"]:
            return "aaa"
        return ""

    with patch.object(module, "run", side_effect=command_output):
        output = module.scope_branch()

    assert "[INFO] No upstream tracking branch configured." in output
    assert not any(command[:2] == ["git", "rev-list"] for command in commands)


def test_scope_branch_compares_configured_upstream():
    module = load_script()
    commands = []

    def command_output(command):
        commands.append(command)
        if command == ["git", "branch", "--show-current"]:
            return "feature"
        if command[:3] == ["git", "for-each-ref", "--format=%(upstream:short)"]:
            return "fork/feature"
        if command == ["git", "rev-list", "--count", "fork/feature..HEAD"]:
            return "2"
        if command == ["git", "rev-list", "--count", "HEAD..fork/feature"]:
            return "1"
        if command[:2] == ["git", "merge-base"]:
            return "aaa"
        return ""

    with patch.object(module, "run", side_effect=command_output):
        output = module.scope_branch()

    assert "[INFO] 2 ahead, 1 behind fork/feature." in output
    assert not any("origin/feature" in argument for command in commands for argument in command)


@pytest.mark.parametrize("status", ["behind", "diverged"])
def test_main_stops_on_unhealthy_branch_without_recovery_commands(status, capsys):
    module = load_script()
    module._commit_base = "aaa"
    health = {"status": status, "ahead": 1, "behind": 2}

    with (
        patch.object(sys, "argv", ["preflight-review.py", "--init-review"]),
        patch.object(module, "scope_other", return_value=[]),
        patch.object(module, "check_unstaged", return_value=[]),
        patch.object(module, "check_branch_health", return_value=health),
        patch.object(module, "init_review") as init_review,
        patch.object(module, "run", return_value="feature"),
        patch.object(Path, "exists", return_value=False),
        pytest.raises(SystemExit) as exit_info,
    ):
        module._main()

    output = capsys.readouterr().out.lower()
    assert exit_info.value.code == 1
    assert f"branch is {status}" in output
    assert not any(word in output for word in ("pull", "stash", "reset"))
    init_review.assert_not_called()


def test_init_review_refuses_to_overwrite_existing_report():
    module = load_script()
    module._commit_base = "aaa"

    with (
        patch.object(module, "run", return_value="bbb"),
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "write_text") as write_text,
        pytest.raises(ValueError, match="already exists"),
    ):
        module.init_review("REVIEW_existing")

    write_text.assert_not_called()


def test_validation_preflight_allows_stale_report_and_unstaged_content(
    tmp_path, capsys
):
    module = load_script()
    report = tmp_path / "REVIEW_test.md"
    report.write_text("review")

    with (
        patch.object(module.repo_guard, "assert_inside_repo", return_value=report),
        patch.object(
            module,
            "parse_review_header",
            return_value={"branch": "feature", "head": "stale"},
        ),
        patch.object(module, "run", return_value="feature"),
        patch.object(
            module,
            "check_branch_health",
            return_value={"status": "ahead", "ahead": 1, "behind": 0},
        ),
        patch.object(module, "check_unstaged", side_effect=AssertionError),
    ):
        assert module.validation_preflight_check_file(str(report)) == 0

    assert "validation preflight passed" in capsys.readouterr().out.lower()


def test_validation_preflight_rejects_malformed_report(tmp_path, capsys):
    module = load_script()
    report = tmp_path / "REVIEW_test.md"
    report.write_text("review")

    with (
        patch.object(module.repo_guard, "assert_inside_repo", return_value=report),
        patch.object(module, "parse_review_header", return_value=None),
    ):
        assert module.validation_preflight_check_file(str(report)) == 1

    assert "not a valid review report" in capsys.readouterr().err.lower()


def test_validation_preflight_rejects_branch_mismatch(tmp_path, capsys):
    module = load_script()
    report = tmp_path / "REVIEW_test.md"
    report.write_text("review")

    with (
        patch.object(module.repo_guard, "assert_inside_repo", return_value=report),
        patch.object(
            module,
            "parse_review_header",
            return_value={"branch": "other-feature", "head": "stale"},
        ),
        patch.object(module, "run", return_value="feature"),
        patch.object(
            module,
            "check_branch_health",
            return_value={"status": "up_to_date", "ahead": 0, "behind": 0},
        ),
    ):
        assert module.validation_preflight_check_file(str(report)) == 1

    assert "branch mismatch" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("status", ["behind", "diverged"])
def test_validation_preflight_rejects_unhealthy_branch(status, tmp_path, capsys):
    module = load_script()
    report = tmp_path / "REVIEW_test.md"
    report.write_text("review")

    with (
        patch.object(module.repo_guard, "assert_inside_repo", return_value=report),
        patch.object(
            module,
            "parse_review_header",
            return_value={"branch": "feature", "head": "stale"},
        ),
        patch.object(module, "run", return_value="feature"),
        patch.object(
            module,
            "check_branch_health",
            return_value={"status": status, "ahead": 1, "behind": 2},
        ),
    ):
        assert module.validation_preflight_check_file(str(report)) == 1

    assert f"branch is {status}" in capsys.readouterr().err.lower()


def test_validation_preflight_rejects_detached_head(tmp_path, capsys):
    module = load_script()
    report = tmp_path / "REVIEW_test.md"
    report.write_text("review")

    with (
        patch.object(module.repo_guard, "assert_inside_repo", return_value=report),
        patch.object(
            module,
            "parse_review_header",
            return_value={"branch": "feature", "head": "stale"},
        ),
        patch.object(module, "run", return_value=""),
        patch.object(
            module,
            "check_branch_health",
            return_value={"status": "detached", "ahead": 0, "behind": 0},
        ),
    ):
        assert module.validation_preflight_check_file(str(report)) == 1

    assert "detached head" in capsys.readouterr().err.lower()
