"""Regression tests for preflight-rebase.py."""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import repo_guard
from cli_common import EXIT_EXTERNAL, ExternalCommandError


ROOT = Path(__file__).parents[3]


def load_script():
    path = Path(__file__).parent.parent / "preflight-rebase.py"
    spec = importlib.util.spec_from_file_location("preflight_rebase", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("conflicts", [True, False])
def test_cli_detects_conflicts_in_disposable_repository(conflicts, capsys):
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
        repo = Path(directory)
        run_git(repo, "init", "-b", "main")
        run_git(repo, "config", "user.name", "Test User")
        run_git(repo, "config", "user.email", "test@example.com")
        (repo / "shared.txt").write_text("base\n")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "base")

        run_git(repo, "checkout", "-b", "feature")
        feature_file = repo / ("shared.txt" if conflicts else "feature.txt")
        feature_file.write_text("feature\n")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "feature change")

        run_git(repo, "checkout", "main")
        main_file = repo / ("shared.txt" if conflicts else "main.txt")
        main_file.write_text("main\n")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "main change")
        run_git(repo, "checkout", "feature")

        module = load_script()
        with (
            patch.object(repo_guard, "_ROOT", repo),
            patch.object(sys, "argv", ["preflight-rebase.py", "--target", "main"]),
            pytest.raises(SystemExit) as exit_info,
        ):
            module.main()

        output = capsys.readouterr().out

    if conflicts:
        assert exit_info.value.code != 0
        assert "[WARN] 1 file(s) may conflict during rebase:" in output
        assert "shared.txt" in output
        assert "git rebase --onto main" in output
        assert "git rebase main`" not in output
    else:
        assert exit_info.value.code == 0
        assert "No merge conflicts detected in dry run" in output


@pytest.mark.parametrize(
    "message",
    [
        "[FAIL] Branch is 2 commit(s) behind @origin/main",
        "[FAIL] Branch has diverged: 1 ahead, 2 behind @origin/main",
    ],
)
def test_main_returns_nonzero_for_failed_upstream_sync(message, capsys):
    module = load_script()

    with (
        patch.object(sys, "argv", ["preflight-rebase.py"]),
        patch.object(module, "check_upstream_sync", return_value=[message]),
        patch.object(module, "check_ahead_behind", return_value=[]),
        patch.object(module, "check_duplicates", return_value=[]),
        patch.object(module, "check_potential_conflicts", return_value=[]),
        patch.object(module, "check_uncommitted", return_value=[]),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    assert exit_info.value.code != 0
    assert message in capsys.readouterr().out


def test_main_returns_external_exit_for_subprocess_failure(capsys):
    module = load_script()
    error = ExternalCommandError(
        ["git", "branch"],
        "Command timed out after 30s: git branch",
    )

    with (
        patch.object(sys, "argv", ["preflight-rebase.py"]),
        patch.object(module, "detect_base", side_effect=error),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    assert exit_info.value.code == EXIT_EXTERNAL
    assert "[FAIL] Command timed out after 30s: git branch" in capsys.readouterr().err


def test_check_pr_base_uses_gh_wrapper():
    module = load_script()

    with patch.object(module, "run_process", return_value="main") as runner:
        assert module.check_pr_base("feature") == "main"

    assert runner.call_args.args[0] == [
        sys.executable,
        str(Path(module.__file__).with_name("gh.py")),
        "cmd",
        "--format",
        "raw",
        "pr",
        "list",
        "--head",
        "feature",
        "--state",
        "open",
        "--json",
        "baseRefName",
        "--jq",
        ".[0].baseRefName",
    ]


def test_main_discovers_target_when_omitted(capsys):
    module = load_script()

    with (
        patch.object(sys, "argv", ["preflight-rebase.py"]),
        patch.object(module, "detect_base", return_value="stack-base") as detect,
        patch.object(module, "check_upstream_sync", return_value=[]),
        patch.object(module, "check_ahead_behind", return_value=[]) as ahead,
        patch.object(module, "check_duplicates", return_value=[]) as duplicates,
        patch.object(module, "check_potential_conflicts", return_value=[]) as conflicts,
        patch.object(module, "check_uncommitted", return_value=[]),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    assert exit_info.value.code == 0
    detect.assert_called_once_with()
    ahead.assert_called_once_with("stack-base")
    duplicates.assert_called_once_with("stack-base")
    conflicts.assert_called_once_with("stack-base")
    assert capsys.readouterr().out == "[OK] Rebase pre-flight checks passed.\n"


def test_main_preserves_explicit_target():
    module = load_script()

    with (
        patch.object(sys, "argv", ["preflight-rebase.py", "--target", "release"]),
        patch.object(module, "detect_base") as detect,
        patch.object(module, "check_upstream_sync", return_value=[]),
        patch.object(module, "check_ahead_behind", return_value=[]) as ahead,
        patch.object(module, "check_duplicates", return_value=[]),
        patch.object(module, "check_potential_conflicts", return_value=[]),
        patch.object(module, "check_uncommitted", return_value=[]),
        pytest.raises(SystemExit),
    ):
        module.main()

    detect.assert_not_called()
    ahead.assert_called_once_with("release")


def test_check_duplicates_uses_git_cherry_equivalence_marker():
    module = load_script()
    output = "- abc123 already applied\n+ def456 unique"

    with patch.object(module, "run_process", return_value=output) as runner:
        messages = module.check_duplicates("main")

    runner.assert_called_once_with(["git", "cherry", "-v", "main", "HEAD"])
    assert messages == [
        "[WARN] 1 commit(s) already in main (will be skipped):",
        "abc123 already applied",
    ]


def test_detect_base_output_fields_are_preserved(capsys):
    module = load_script()

    with (
        patch.object(sys, "argv", ["preflight-rebase.py", "--detect-base"]),
        patch.object(module, "get_current_branch", return_value="feature"),
        patch.object(module, "detect_base", return_value="stack-base"),
        patch.object(module, "check_pr_base", return_value="stack-base"),
        patch.object(module, "get_unique_commits", return_value=["abc change"]),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.splitlines() == [
        "branch=feature",
        "base=stack-base",
        "source=pr (target of open PR for feature)",
        "unique_commits=1",
        "stacked=true",
    ]
