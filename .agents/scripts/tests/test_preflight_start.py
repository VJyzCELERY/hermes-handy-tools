"""Regression tests for preflight-start.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def load_script():
    path = Path(__file__).parent.parent / "preflight-start.py"
    spec = importlib.util.spec_from_file_location("preflight_start", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def successful_process(command, **_kwargs):
    if command[:3] == ["git", "branch", "--show-current"]:
        return "feature"
    if command[:4] == ["git", "config", "--local", "--get"]:
        return "main"
    if command[0] == sys.executable:
        return '[{"number": 12}]'
    raise AssertionError(f"Unexpected command: {command}")


def test_main_is_read_only_and_uses_verified_root(monkeypatch, capsys):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    commands = []

    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)

    def record_process(command, **kwargs):
        commands.append((command, kwargs))
        return successful_process(command, **kwargs)

    monkeypatch.setattr(module, "run_process", record_process)
    monkeypatch.setattr(
        Path,
        "mkdir",
        lambda *_args, **_kwargs: pytest.fail(
            "session preflight must not create paths"
        ),
    )

    assert module.main([]) == 0

    output = capsys.readouterr().out
    assert f"[BOUNDARY] Project root: {root}" in output
    assert "Do NOT operate outside" not in output
    assert "[GIT] Branch: feature" in output
    assert "[GIT] Base branch: main" in output
    assert "[GIT] PR: #12" in output
    assert "is ready" not in output
    assert all(kwargs.get("cwd") == root for _, kwargs in commands)
    assert any(
        command[:4]
        == [sys.executable, str(root / ".agents/scripts/gh.py"), "cmd", "--format"]
        for command, _ in commands
    )
    assert all(command[0] != "gh" for command, _ in commands)


def test_main_external_failure_returns_three_with_context(monkeypatch, capsys):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)
    monkeypatch.setattr(
        module,
        "run_process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            module.ExternalCommandError(["git"], "git unavailable")
        ),
    )

    assert module.main([]) == 3

    captured = capsys.readouterr()
    assert "[OS]" in captured.out
    assert f"[BOUNDARY] Project root: {root}" in captured.out
    assert "git unavailable" in captured.err


def test_main_github_failure_reports_pr_unavailable(monkeypatch, capsys):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)

    def failed_github(command, **kwargs):
        if command[0] == sys.executable:
            raise module.ExternalCommandError(command, "GitHub unavailable")
        return successful_process(command, **kwargs)

    monkeypatch.setattr(module, "run_process", failed_github)

    assert module.main([]) == 0

    captured = capsys.readouterr()
    assert "[GIT] Branch: feature" in captured.out
    assert "[GIT] Base branch: main" in captured.out
    assert "[GIT] PR: unavailable" in captured.out
    assert "GitHub unavailable" in captured.err


def test_main_json_format_is_machine_readable(monkeypatch, capsys):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)
    monkeypatch.setattr(module, "run_process", successful_process)

    assert module.main(["--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["boundary"]["root"] == str(root)
    assert payload["git"] == {"branch": "feature", "base_branch": "main", "pr": 12}


@pytest.mark.parametrize("output", ["not-json", "{}", "[1]"])
def test_main_malformed_pr_json_reports_unavailable(monkeypatch, capsys, output):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)

    def malformed_pr(command, **kwargs):
        if command[0] == sys.executable:
            return output
        return successful_process(command, **kwargs)

    monkeypatch.setattr(module, "run_process", malformed_pr)

    assert module.main([]) == 0

    captured = capsys.readouterr()
    assert "[GIT] PR: unavailable" in captured.out
    assert "invalid JSON" in captured.err


def test_main_json_github_failure_keeps_pr_null(monkeypatch, capsys):
    module = load_script()
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(module.repo_guard, "repo_root", lambda: root)

    def failed_github(command, **kwargs):
        if command[0] == sys.executable:
            raise module.ExternalCommandError(command, "GitHub unavailable")
        return successful_process(command, **kwargs)

    monkeypatch.setattr(module, "run_process", failed_github)

    assert module.main(["--format", "json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["git"] == {"branch": "feature", "base_branch": "main", "pr": None}
    assert "GitHub unavailable" in captured.err
