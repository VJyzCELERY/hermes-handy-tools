"""Shared subprocess behavior for agent command-line scripts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import repo_guard

EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_EXTERNAL = 3
EXIT_PARTIAL = 4
DEFAULT_TIMEOUT = 30


class ExternalCommandError(RuntimeError):
    """An external command could not complete successfully."""

    def __init__(
        self,
        command: Sequence[str],
        message: str,
        *,
        returncode: int = EXIT_EXTERNAL,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_process(
    command: Sequence[str],
    *,
    input_data: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | Path | None = None,
) -> str:
    """Run a command and return stdout, preserving failures as exceptions."""
    workdir = repo_guard.assert_inside_repo(cwd or repo_guard.repo_root())
    try:
        result = subprocess.run(
            list(command),
            cwd=workdir,
            text=True,
            capture_output=True,
            input=input_data,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise ExternalCommandError(
            command,
            f"Command not found: {command[0]}",
            stderr=str(error),
        ) from error
    except subprocess.TimeoutExpired as error:
        stderr = error.stderr or ""
        raise ExternalCommandError(
            command,
            f"Command timed out after {timeout}s: {' '.join(command)}",
            stderr=stderr if isinstance(stderr, str) else stderr.decode(),
        ) from error

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode:
        detail = stderr or stdout or "no diagnostic output"
        raise ExternalCommandError(
            command,
            f"Command failed ({result.returncode}): {' '.join(command)}: {detail}",
            returncode=result.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    return stdout
