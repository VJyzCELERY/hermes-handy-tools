"""Tests for updating review commit ranges safely."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "update_commit_range", SCRIPTS / "update-commit-range.py"
)
update_commit_range = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(update_commit_range)

BASE = "a" * 40
NON_MAIN_BASE = "d" * 40
OLD_HEAD = "b" * 40
HEAD = "c" * 40


def review(range_value=f"{BASE}...{OLD_HEAD}"):
    """Return a minimal review report."""
    return f"# Review\n**Reviewer**: Test\n**Commit Range**: {range_value}\n"


def healthy_git(command):
    """Return deterministic output for a healthy local branch."""
    outputs = {
        ("git", "branch", "--show-current"): "feature",
        ("git", "rev-parse", "HEAD"): HEAD,
        (
            "git",
            "for-each-ref",
            "--format=%(upstream:short)",
            "refs/heads/feature",
        ): "origin/feature",
        (
            "git",
            "rev-list",
            "--left-right",
            "--count",
            "HEAD...origin/feature",
        ): "0\t0",
        ("git", "merge-base", "main", "HEAD"): BASE,
    }
    return outputs[tuple(command)]


def test_parser_supports_help_and_positional_review_path(capsys):
    parser = update_commit_range.build_parser()

    args = parser.parse_args(["reviews/report.md"])

    assert args.review_path == "reviews/report.md"
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["--help"])
    assert error.value.code == 0
    assert "review_path" in capsys.readouterr().out


def test_main_updates_valid_range_atomically(tmp_path, monkeypatch):
    path = tmp_path / "review.md"
    path.write_text(review(), encoding="utf-8")
    replacements = []
    real_replace = update_commit_range.os.replace

    def replace(source, destination):
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(update_commit_range, "run_process", healthy_git)
    monkeypatch.setattr(update_commit_range.os, "replace", replace)

    result = update_commit_range.main([str(path)])

    assert result == 0
    assert path.read_text(encoding="utf-8") == review(f"{BASE}...{HEAD}")
    assert len(replacements) == 1
    assert replacements[0][0].parent == path.parent
    assert replacements[0][1] == path


def test_main_preserves_existing_base_sha(tmp_path, monkeypatch):
    path = tmp_path / "review.md"
    path.write_text(review(f"{NON_MAIN_BASE}...{OLD_HEAD}"), encoding="utf-8")
    commands = []

    def git(command):
        commands.append(command)
        return healthy_git(command)

    monkeypatch.setattr(update_commit_range, "run_process", git)

    assert update_commit_range.main([str(path)]) == 0
    assert path.read_text(encoding="utf-8") == review(f"{NON_MAIN_BASE}...{HEAD}")
    assert ["git", "merge-base", "main", "HEAD"] not in commands


@pytest.mark.parametrize(
    "content",
    [
        "# Review\n**Reviewer**: Test\n",
        "# Review\n**Commit Range**: invalid\n",
        f"# Review\n**Commit Range** {BASE}...{OLD_HEAD}\n",
        review() + f"**Commit Range**: {BASE}...{OLD_HEAD}\n",
    ],
)
def test_main_rejects_missing_or_malformed_commit_range(tmp_path, monkeypatch, content):
    path = tmp_path / "review.md"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(update_commit_range, "run_process", healthy_git)

    result = update_commit_range.main([str(path)])

    assert result == 1
    assert path.read_text(encoding="utf-8") == content


def test_main_rejects_directory(tmp_path):
    assert update_commit_range.main([str(tmp_path)]) == 1


@pytest.mark.parametrize("counts", ["0\t2", "1\t2"])
def test_main_does_not_write_when_branch_is_stale(tmp_path, monkeypatch, counts):
    path = tmp_path / "review.md"
    original = review()
    path.write_text(original, encoding="utf-8")

    def stale_git(command):
        if command[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return counts
        return healthy_git(command)

    monkeypatch.setattr(update_commit_range, "run_process", stale_git)

    result = update_commit_range.main([str(path)])

    assert result == 1
    assert path.read_text(encoding="utf-8") == original


def test_main_reports_git_failure_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "review.md"
    original = review()
    path.write_text(original, encoding="utf-8")

    def failed_git(command):
        raise update_commit_range.ExternalCommandError(command, "Command timed out")

    monkeypatch.setattr(update_commit_range, "run_process", failed_git)

    result = update_commit_range.main([str(path)])

    assert result == update_commit_range.EXIT_EXTERNAL
    assert path.read_text(encoding="utf-8") == original
