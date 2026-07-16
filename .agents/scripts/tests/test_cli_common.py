"""Tests for shared agent-script process handling."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import cli_common


def test_run_process_preserves_failure_details(monkeypatch):
    failure = subprocess.CompletedProcess(
        ["tool"], returncode=7, stdout="partial", stderr="broken"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: failure)

    with pytest.raises(cli_common.ExternalCommandError) as error:
        cli_common.run_process(["tool"])

    assert error.value.returncode == 7
    assert error.value.stdout == "partial"
    assert error.value.stderr == "broken"


def test_run_process_reports_missing_command(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("tool")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(cli_common.ExternalCommandError, match="not found"):
        cli_common.run_process(["tool"])


def test_run_process_reports_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["tool"], timeout=5, stderr="too slow")

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(cli_common.ExternalCommandError, match="timed out"):
        cli_common.run_process(["tool"], timeout=5)


def test_run_process_uses_repository_root(monkeypatch):
    captured = {}

    def run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "ok\n", "")

    monkeypatch.setattr(subprocess, "run", run)

    result = cli_common.run_process(["tool"])

    assert result == "ok"
    assert Path(captured["cwd"]) == cli_common.repo_guard.repo_root()
