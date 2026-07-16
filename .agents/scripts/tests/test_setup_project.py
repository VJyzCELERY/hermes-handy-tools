"""Behavior tests for version-driven template infrastructure updates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

import repo_guard  # noqa: E402
import setup_project  # noqa: E402


def git(path: Path, *args: str) -> None:
    """Run Git for a compact local template fixture."""
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)


def write_marker(root: Path, version: int) -> None:
    """Write the release marker used by a fixture version."""
    marker = root / ".agents" / "template-version.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"version": version, "tag": f"template-v{version}"}) + "\n",
        encoding="utf-8",
    )


def template_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Create a version-1 project and a version-2 tagged template source."""
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "AGENTS.md").write_text("# Template\n", encoding="utf-8")
    (source / ".agents" / "commands").mkdir(parents=True)
    (source / ".agents" / "commands" / "example.md").write_text("one\n", encoding="utf-8")
    write_marker(source, 1)
    git(source, "add", ".")
    git(source, "commit", "-m", "version 1")
    git(source, "tag", "template-v1")

    (source / ".agents" / "commands" / "example.md").write_text("two\n", encoding="utf-8")
    (source / ".agents" / "commands" / "added.md").write_text("new\n", encoding="utf-8")
    write_marker(source, 2)
    git(source, "add", ".")
    git(source, "commit", "-m", "version 2")

    project = tmp_path / "project"
    project.mkdir()
    git(project, "init")
    (project / "AGENTS.md").write_text("# Project\n", encoding="utf-8")
    (project / ".agents" / "commands").mkdir(parents=True)
    (project / ".agents" / "commands" / "example.md").write_text("one\n", encoding="utf-8")
    write_marker(project, 1)
    return project, source


@pytest.fixture
def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point repository guards at a disposable project fixture."""
    project, source = template_fixture(tmp_path)
    monkeypatch.setattr(repo_guard, "_ROOT", project)
    return project, source


def test_preview_current_skips_managed_file_comparison(fixture: tuple[Path, Path]) -> None:
    """Equal markers return before managed infrastructure is inspected."""
    project, source = fixture
    write_marker(project, 2)
    (project / ".agents" / "commands" / "example.md").unlink()

    preview = setup_project.prepare_update(str(source))

    assert preview.status == "current"
    assert preview.actions == ()


def test_preview_rejects_downgrade(fixture: tuple[Path, Path]) -> None:
    """An older incoming marker is never considered for application."""
    project, source = fixture
    write_marker(project, 3)

    with pytest.raises(setup_project.UpdateError, match="downgrade"):
        setup_project.prepare_update(str(source))


def test_preview_rejects_tmp_symlink_without_touching_external_clone(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    """A repository tmp symlink cannot direct clone cleanup outside the project."""
    project, source = fixture
    external_clone = tmp_path / "external" / setup_project.CLONE_NAME
    external_clone.mkdir(parents=True)
    sentinel = external_clone / "keep"
    sentinel.write_text("keep\n", encoding="utf-8")
    (project / "tmp").symlink_to(external_clone.parent, target_is_directory=True)

    with pytest.raises(setup_project.UpdateError, match="tmp.*symlink"):
        setup_project.prepare_update(str(source))

    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_preview_uses_installed_tag_for_three_way_baseline(
    fixture: tuple[Path, Path],
) -> None:
    """The v1 tag distinguishes an upstream change from a local edit."""
    project, source = fixture
    (project / ".agents" / "commands" / "example.md").write_text(
        "local\n", encoding="utf-8"
    )

    preview = setup_project.prepare_update(str(source))

    assert preview.status == "upgrade"
    assert preview.conflicts == ("commands/example.md",)
    assert {action.path: action.kind for action in preview.actions} == {
        "commands/added.md": "add",
        "commands/example.md": "conflict",
    }


def test_apply_updates_only_upstream_changes_and_finalizes_marker(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirmed non-conflicting actions update files before the marker."""
    project, source = fixture
    preview = setup_project.prepare_update(str(source))
    monkeypatch.setattr(setup_project, "run_preflight", lambda: None)

    setup_project.apply_update(preview, confirmed=True)

    assert (project / ".agents" / "commands" / "example.md").read_text() == "two\n"
    assert (project / ".agents" / "commands" / "added.md").read_text() == "new\n"
    assert json.loads((project / ".agents" / "template-version.json").read_text())["version"] == 2
    assert not (project / "tmp" / "setup-project-template").exists()


def test_apply_preserves_project_only_changes(fixture: tuple[Path, Path]) -> None:
    """A local-only file is untouched by a template upgrade."""
    project, source = fixture
    local = project / ".agents" / "commands" / "local.md"
    local.write_text("keep\n", encoding="utf-8")

    preview = setup_project.prepare_update(str(source))

    assert "commands/local.md" not in {action.path for action in preview.actions}
    assert local.read_text() == "keep\n"


def test_apply_removes_files_unchanged_from_installed_tag(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upstream removal deletes only a file still matching the baseline."""
    project, source = fixture
    (source / ".agents" / "commands" / "example.md").unlink()
    git(source, "add", "-u")
    git(source, "commit", "-m", "remove example")
    preview = setup_project.prepare_update(str(source))
    monkeypatch.setattr(setup_project, "run_preflight", lambda: None)

    setup_project.apply_update(preview, confirmed=True)

    assert not (project / ".agents" / "commands" / "example.md").exists()


def test_apply_refuses_conflicts_without_advancing_marker(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Divergent edits stop before a local file or its marker is replaced."""
    project, source = fixture
    local = project / ".agents" / "commands" / "example.md"
    local.write_text("local\n", encoding="utf-8")
    preview = setup_project.prepare_update(str(source))
    monkeypatch.setattr(setup_project, "run_preflight", lambda: None)

    with pytest.raises(setup_project.UpdateError, match="conflict"):
        setup_project.apply_update(preview, confirmed=True)

    assert local.read_text() == "local\n"
    assert json.loads((project / ".agents" / "template-version.json").read_text())["version"] == 1


def test_apply_failure_does_not_finalize_marker(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem safety failure leaves the installed marker unchanged."""
    project, source = fixture
    preview = setup_project.prepare_update(str(source))
    target = project / ".agents" / "commands" / "example.md"
    target.unlink()
    target.symlink_to("../../AGENTS.md")
    monkeypatch.setattr(setup_project, "run_preflight", lambda: None)

    with pytest.raises(setup_project.UpdateError, match="symlink"):
        setup_project.apply_update(preview, confirmed=True)

    assert json.loads((project / ".agents" / "template-version.json").read_text())["version"] == 1


def test_apply_preflight_failure_does_not_finalize_marker(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed preflight leaves the installed marker at its prior version."""
    project, source = fixture
    preview = setup_project.prepare_update(str(source))

    def fail_preflight() -> None:
        raise setup_project.UpdateError("preflight failed")

    monkeypatch.setattr(setup_project, "run_preflight", fail_preflight)

    with pytest.raises(setup_project.UpdateError, match="preflight failed"):
        setup_project.apply_update(preview, confirmed=True)

    assert json.loads((project / ".agents" / "template-version.json").read_text())["version"] == 1


def test_legacy_preview_adds_only_missing_files(fixture: tuple[Path, Path]) -> None:
    """Markerless projects never replace existing managed files."""
    project, source = fixture
    (project / ".agents" / "template-version.json").unlink()

    preview = setup_project.prepare_update(str(source))

    assert preview.status == "legacy"
    assert {action.path: action.kind for action in preview.actions} == {
        "commands/added.md": "add"
    }


def test_preview_rejects_unsafe_path_and_symlink(fixture: tuple[Path, Path]) -> None:
    """Managed symlinks are rejected before preview creates writable state."""
    project, source = fixture
    (source / ".agents" / "commands" / "unsafe.md").symlink_to("../../AGENTS.md")
    git(source, "add", ".")
    git(source, "commit", "-m", "unsafe")

    with pytest.raises(setup_project.UpdateError, match="symlink"):
        setup_project.prepare_update(str(source))

    assert not (project / "tmp" / "setup-project-template").exists()


def test_apply_requires_confirmation_and_preserves_existing_alias(
    fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply is confirmation-gated and never replaces an existing harness alias."""
    project, source = fixture
    alias = project / ".opencode"
    alias.write_text("local alias\n", encoding="utf-8")
    preview = setup_project.prepare_update(str(source))
    monkeypatch.setattr(setup_project, "run_preflight", lambda: None)

    with pytest.raises(setup_project.UpdateError, match="confirmation"):
        setup_project.apply_update(preview, confirmed=False)
    setup_project.apply_update(preview, confirmed=True)

    assert alias.read_text() == "local alias\n"
    assert (project / ".codex").is_symlink()


def test_setup_project_command_replaces_inline_guide_lookup() -> None:
    """The command removes the inline shell in favor of the preflight CLI."""
    command = (ROOT / ".agents" / "commands" / "setup-project.md").read_text(
        encoding="utf-8"
    )
    lookup = (
        "(\n"
        "  uv run python .agents/scripts/gh.py cmd --format raw api \\\n"
        "    repos/VJyzCELERY/MAIN-PROJECT-TEMPLATE/issues/17 --jq .html_url \\\n"
        "    || {\n"
        "      printf '%s\\n' \\\n"
        "        'Unable to retrieve the canonical guide: current GitHub authentication may "
        "not access the private template repository.' >&2\n"
        "      false\n"
        "    }\n"
        ")"
    )

    assert lookup not in command
    lookup = "uv run python .agents/scripts/setup_project_preflight.py"

    assert lookup in command
    assert command.index(lookup) < command.index("Preview through the version-driven updater")
    assert 'uv run python .agents/scripts/setup_project.py preview . "$TEMPLATE_URL"' in command
    assert "uv run python .agents/scripts/setup_project.py apply . --confirm" in command
