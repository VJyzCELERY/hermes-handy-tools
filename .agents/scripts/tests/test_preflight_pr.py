"""Regression tests for preflight-pr.py."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def load_script():
    path = Path(__file__).parent.parent / "preflight-pr.py"
    spec = importlib.util.spec_from_file_location("preflight_pr", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_for_branch(module, output=None, error=None):
    with (
        patch.object(sys, "argv", ["preflight-pr.py", "--branch", "feature"]),
        patch.object(module, "run_process", return_value=output, side_effect=error),
        pytest.raises(SystemExit) as exit_info,
    ):
        module.main()
    return exit_info.value.code


def test_malformed_github_json_is_reported_without_traceback(capsys):
    module = load_script()

    code = run_for_branch(module, output="{not-json")

    captured = capsys.readouterr()
    assert code != 0
    assert "json" in (captured.out + captured.err).lower()


def test_external_failure_is_distinguishable_from_no_pr(capsys):
    module = load_script()
    failure = module.ExternalCommandError(
        ["gh", "pr", "list"],
        "authentication failed",
        stderr="authentication failed",
    )

    external_failure_code = run_for_branch(module, error=failure)
    external_failure_output = capsys.readouterr()
    no_pr_code = run_for_branch(module, output="[]")
    capsys.readouterr()

    assert external_failure_code == 3
    assert "authentication failed" in (
        external_failure_output.out + external_failure_output.err
    )
    assert no_pr_code == 1


def test_find_pr_routes_github_operation_through_gh_py():
    module = load_script()

    with patch.object(module, "run_process", return_value="[]") as run:
        module.find_pr("feature")

    command = run.call_args.args[0]
    assert command[:5] == [
        sys.executable,
        str(Path(module.__file__).parent / "gh.py"),
        "cmd",
        "--format",
        "raw",
    ]
    assert command[5:] == [
        "pr",
        "list",
        "--head",
        "feature",
        "--state",
        "open",
        "--json",
        "number,headRefName,baseRefName,title,state",
    ]


def test_validate_pr_routes_github_operation_through_gh_py():
    module = load_script()

    with patch.object(module, "run_process", return_value='{"number": 7}') as run:
        assert module.validate_pr("7") == {"number": 7}

    assert run.call_args.args[0] == [
        sys.executable,
        str(Path(module.__file__).parent / "gh.py"),
        "cmd",
        "--format",
        "raw",
        "pr",
        "view",
        "7",
        "--json",
        "number,headRefName,baseRefName,title,state",
    ]
