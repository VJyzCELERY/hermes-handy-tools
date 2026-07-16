"""Public behavior tests for the setup-project wiki preflight."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

import repo_guard  # noqa: E402
import setup_project_preflight  # noqa: E402


ACCESS_ERROR = (
    "Install and authenticate `gh`; the current account may not access the private "
    "template repository."
)


REPOSITORY_RESPONSE = (
    '{"full_name": "VJyzCELERY/MAIN-PROJECT-TEMPLATE", '
    '"html_url": "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE", '
    '"has_wiki": true}'
)


def completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Create the wrapped GitHub command result used by the public CLI."""
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


@pytest.fixture
def clone_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Contain the fixed wiki clone directory in an isolated repository root."""
    root = tmp_path / "repository"
    (root / "tmp").mkdir(parents=True)
    monkeypatch.setattr(repo_guard, "_ROOT", root)
    return root / "tmp" / setup_project_preflight.WIKI_CLONE_NAME


def test_preflight_prints_agents_guide_and_canonical_wiki_url(
    clone_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A validated wiki prints the detailed Agents guide and canonical URL."""
    commands: list[list[str]] = []

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args[-1] == setup_project_preflight.REPOSITORY_ROUTE:
            return completed(REPOSITORY_RESPONSE)
        clone_dir.mkdir()
        (clone_dir / "Home.md").write_text("Do not read this guide.\n", encoding="utf-8")
        (clone_dir / "Agents.md").write_text(
            "# Agents Guide\n\n## Install\nRun this first.\n\n## Update\nRun this after.\n",
            encoding="utf-8",
        )
        return completed()

    monkeypatch.setattr(setup_project_preflight.subprocess, "run", run)

    assert setup_project_preflight.main([]) == 0
    assert capsys.readouterr().out == (
        "# Agents Guide\n\n## Install\nRun this first.\n\n## Update\nRun this after.\n"
        "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE/wiki\n"
    )
    assert not clone_dir.exists()
    assert commands == [
        [
            sys.executable,
            str(ROOT / ".agents" / "scripts" / "gh.py"),
            "cmd",
            "--format",
            "json",
            "api",
            "repos/VJyzCELERY/MAIN-PROJECT-TEMPLATE",
        ],
        [
            sys.executable,
            str(ROOT / ".agents" / "scripts" / "gh.py"),
            "cmd",
            "--format",
            "raw",
            "repo",
            "clone",
            "VJyzCELERY/MAIN-PROJECT-TEMPLATE.wiki",
            str(clone_dir),
            "--",
            "--depth",
            "1",
        ],
    ]


def test_preflight_reports_missing_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing CLI produces the safe actionable error."""
    monkeypatch.setattr(
        setup_project_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err


def test_preflight_reports_repository_access_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed repository request does not expose its wrapped error."""
    monkeypatch.setattr(
        setup_project_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: completed("secret", 1, "private failure"),
    )

    assert setup_project_preflight.main([]) != 0
    output = capsys.readouterr().err
    assert ACCESS_ERROR in output
    assert "secret" not in output
    assert "private failure" not in output


def test_preflight_reports_wiki_retrieval_failure(
    clone_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed wiki clone uses the generic error and cleans its fixed path."""
    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == setup_project_preflight.REPOSITORY_ROUTE:
            return completed(REPOSITORY_RESPONSE)
        clone_dir.mkdir()
        return completed("", 1, "private failure")

    monkeypatch.setattr(setup_project_preflight.subprocess, "run", run)

    assert setup_project_preflight.main([]) != 0
    output = capsys.readouterr().err
    assert ACCESS_ERROR in output
    assert "private failure" not in output
    assert not clone_dir.exists()


def test_preflight_rejects_mismatched_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A response for another repository is not accepted as canonical."""
    response = (
        '{"full_name": "VJyzCELERY/OTHER-REPOSITORY", '
        '"html_url": "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE", '
        '"has_wiki": true}'
    )
    monkeypatch.setattr(
        setup_project_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: completed(response),
    )

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err


def test_preflight_rejects_wiki_disabled_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A canonical repository without a wiki cannot provide the guide."""
    response = (
        '{"full_name": "VJyzCELERY/MAIN-PROJECT-TEMPLATE", '
        '"html_url": "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE", '
        '"has_wiki": false}'
    )
    monkeypatch.setattr(
        setup_project_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: completed(response),
    )

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["missing", "symlink"])
def test_preflight_rejects_unsafe_or_missing_agents_guide(
    kind: str,
    clone_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Agents.md must be regular, and the fixed clone is always removed."""
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == setup_project_preflight.REPOSITORY_ROUTE:
            return completed(REPOSITORY_RESPONSE)
        clone_dir.mkdir()
        if kind == "symlink":
            (clone_dir / "Agents.md").symlink_to(outside)
        return completed()

    monkeypatch.setattr(setup_project_preflight.subprocess, "run", run)

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err
    assert not clone_dir.exists()
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_preflight_cleanup_does_not_follow_a_stale_clone_symlink(
    clone_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale fixed-path symlink is removed without touching its target."""
    preserved = clone_dir.parent / "preserved"
    preserved.mkdir()
    marker = preserved / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    clone_dir.symlink_to(preserved, target_is_directory=True)

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == setup_project_preflight.REPOSITORY_ROUTE:
            return completed(REPOSITORY_RESPONSE)
        clone_dir.mkdir()
        (clone_dir / "Agents.md").write_text("guide\n", encoding="utf-8")
        return completed()

    monkeypatch.setattr(setup_project_preflight.subprocess, "run", run)

    assert setup_project_preflight.main([]) == 0
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert not clone_dir.exists()


def test_preflight_rejects_symlinked_tmp_without_touching_external_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked temporary directory cannot direct preflight outside the repo."""
    root = tmp_path / "repository"
    root.mkdir()
    external = tmp_path / "external"
    external_clone = external / setup_project_preflight.WIKI_CLONE_NAME
    external_clone.mkdir(parents=True)
    marker = external_clone / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    (root / "tmp").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(repo_guard, "_ROOT", root)
    commands: list[list[str]] = []

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return completed(REPOSITORY_RESPONSE)

    monkeypatch.setattr(setup_project_preflight.subprocess, "run", run)

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err
    assert commands == [
        [
            sys.executable,
            str(ROOT / ".agents" / "scripts" / "gh.py"),
            "cmd",
            "--format",
            "json",
            "api",
            "repos/VJyzCELERY/MAIN-PROJECT-TEMPLATE",
        ]
    ]
    assert marker.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        "{}",
        '{"full_name": "", "html_url": "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE", "has_wiki": true}',
        '{"full_name": "VJyzCELERY/MAIN-PROJECT-TEMPLATE", "html_url": "", "has_wiki": true}',
        '{"full_name": "VJyzCELERY/MAIN-PROJECT-TEMPLATE", "html_url": "https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE", "has_wiki": "true"}',
    ],
)
def test_preflight_rejects_malformed_repository_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], response: str
) -> None:
    """Malformed JSON and repository values use the safe actionable error."""
    monkeypatch.setattr(
        setup_project_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: completed(response),
    )

    assert setup_project_preflight.main([]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err


def test_preflight_rejects_unexpected_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    """The public command accepts no positional or option arguments."""
    assert setup_project_preflight.main(["--help"]) != 0
    assert ACCESS_ERROR in capsys.readouterr().err


def test_setup_project_command_uses_one_line_preflight() -> None:
    """The command documents only the preflight before retained updater commands."""
    command = (ROOT / ".agents" / "commands" / "setup-project.md").read_text(
        encoding="utf-8"
    )
    preflight = "uv run python .agents/scripts/setup_project_preflight.py"

    assert command.count(preflight) == 1
    assert command.index(preflight) < command.index("Preview through the version-driven updater")
    assert 'uv run python .agents/scripts/setup_project.py preview . "$TEMPLATE_URL"' in command
    assert "uv run python .agents/scripts/setup_project.py apply . --confirm" in command
    assert ".agents/scripts/gh.py cmd" not in command
