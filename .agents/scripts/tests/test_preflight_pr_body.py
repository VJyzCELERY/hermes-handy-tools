"""Regression tests for preflight-pr-body.py."""

import importlib.util
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest


def load_script():
    scripts_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "preflight_pr_body", scripts_dir / "preflight-pr-body.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sandbox():
    path = Path(__file__).parents[3] / "tmp" / f"preflight-pr-body-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def run_main(module, argv, repo_root):
    with (
        patch.object(sys, "argv", ["preflight-pr-body.py", *argv]),
        patch.object(module, "run_process", return_value=str(repo_root)),
    ):
        return module.main()


def test_positional_spec_outputs_extracted_values_only_to_stdout(sandbox, capsys):
    module = load_script()
    spec = sandbox / "spec.md"
    design = sandbox / "design.md"
    spec.write_text(
        "# Feature Specification: Safer PR Bodies\n\n"
        "**Subproject(s) Affected**: Agent scripts\n\n"
        "- **FR-001**: Reject unsafe paths.\n",
        encoding="utf-8",
    )
    design.write_text("# Design Document: Safer PR Bodies\n", encoding="utf-8")

    code = run_main(module, [str(spec)], sandbox)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert "Safer PR Bodies" in captured.out
    assert "Agent scripts" in captured.out
    assert "FR-001" in captured.out
    assert str(spec) not in captured.out
    assert "`spec.md`" in captured.out
    assert "`design.md`" in captured.out


def test_spec_option_remains_supported(sandbox, capsys):
    module = load_script()
    spec = sandbox / "spec.md"
    spec.write_text("# Feature Specification: Compatible CLI\n", encoding="utf-8")

    code = run_main(module, ["--spec", str(spec)], sandbox)

    assert code == 0
    assert "Compatible CLI" in capsys.readouterr().out


@pytest.mark.parametrize("option", ["spec", "design", "auto-design"])
def test_paths_reject_symlink_escapes(sandbox, capsys, option):
    module = load_script()
    repo = sandbox / "repo"
    outside = sandbox / "outside"
    repo.mkdir()
    outside.mkdir()
    outside_spec = outside / "spec.md"
    outside_design = outside / "design.md"
    outside_spec.write_text("# Feature Specification: Escaped\n", encoding="utf-8")
    outside_design.write_text("# Design Document: Escaped\n", encoding="utf-8")
    spec = repo / "spec.md"
    spec.write_text("# Feature Specification: Safe\n", encoding="utf-8")

    if option == "spec":
        spec.unlink()
        spec.symlink_to(outside_spec)
        argv = [str(spec)]
    elif option == "design":
        design = repo / "design.md"
        design.symlink_to(outside_design)
        argv = [str(spec), "--design", str(design)]
    else:
        (repo / "design.md").symlink_to(outside_design)
        argv = [str(spec)]

    code = run_main(module, argv, repo)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "outside the repository" in captured.err.lower()


def test_path_rejects_parent_traversal(sandbox, capsys):
    module = load_script()
    repo = sandbox / "repo"
    repo.mkdir()
    escaped = sandbox / "spec.md"
    escaped.write_text("# Feature Specification: Escaped\n", encoding="utf-8")

    code = run_main(module, [str(repo / ".." / "spec.md")], repo)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "outside the repository" in captured.err.lower()


def test_missing_spec_is_validation_failure(sandbox, capsys):
    module = load_script()

    code = run_main(module, [str(sandbox / "missing.md")], sandbox)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "not found" in captured.err.lower()


def test_external_git_failure_has_distinct_exit(sandbox, capsys):
    module = load_script()
    failure = module.ExternalCommandError(
        ["git", "rev-parse", "--show-toplevel"],
        "Command failed (128): git repository unavailable",
        returncode=128,
        stderr="git repository unavailable",
    )
    with (
        patch.object(sys, "argv", ["preflight-pr-body.py", "spec.md"]),
        patch.object(module, "run_process", side_effect=failure),
    ):
        code = module.main()

    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    assert "git repository unavailable" in captured.err


def test_missing_git_metadata_is_validation_failure(capsys):
    module = load_script()
    with (
        patch.object(sys, "argv", ["preflight-pr-body.py", "spec.md"]),
        patch.object(module, "run_process", return_value=""),
    ):
        code = module.main()

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "repository root" in captured.err.lower()


def test_help_is_available(capsys):
    module = load_script()
    with (
        patch.object(sys, "argv", ["preflight-pr-body.py", "--help"]),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()

    captured = capsys.readouterr()
    assert exit_info.value.code == 0
    assert "usage:" in captured.out.lower()
    assert "spec" in captured.out.lower()
    assert captured.err == ""
