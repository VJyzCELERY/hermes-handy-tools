"""Tests for repo_guard.py — repo-boundary and temp-path enforcement."""

import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import repo_guard


PROJECT_ROOT = repo_guard.repo_root()


class TestAssertInsideRepo:
    def test_accepts_root_path(self):
        repo_guard.assert_inside_repo(PROJECT_ROOT)

    def test_accepts_nested_path(self):
        nested = PROJECT_ROOT / "src" / "my-subproject"
        repo_guard.assert_inside_repo(nested)

    def test_accepts_dot_agents(self):
        path = PROJECT_ROOT / ".agents" / "scripts"
        repo_guard.assert_inside_repo(path)

    def test_rejects_parent_directory(self):
        parent = PROJECT_ROOT.parent
        with pytest.raises(ValueError, match="escapes the repository root"):
            repo_guard.assert_inside_repo(parent)

    def test_rejects_unrelated_path(self):
        with pytest.raises(ValueError, match="escapes the repository root"):
            repo_guard.assert_inside_repo(PROJECT_ROOT.parent / "unrelated")

    def test_rejects_symlink_escaping(self):
        link = PROJECT_ROOT / "tmp" / "escape-link"
        try:
            link.symlink_to(PROJECT_ROOT.parent, target_is_directory=True)
            with pytest.raises(ValueError, match="escapes the repository root"):
                repo_guard.assert_inside_repo(link)
        finally:
            if link.is_symlink():
                link.unlink()

    def test_rejects_path_with_dot_dot(self):
        malicious = PROJECT_ROOT / ".." / "etc"
        with pytest.raises(ValueError, match="escapes the repository root"):
            repo_guard.assert_inside_repo(malicious)

    def test_bypass_scope_allows_declared_external_root_only_temporarily(self):
        external = PROJECT_ROOT.parent / "external-worktree"

        with repo_guard.bypass_guard([PROJECT_ROOT.parent]):
            assert repo_guard.assert_inside_repo(external) == external.resolve()

        with pytest.raises(ValueError, match="escapes the repository root"):
            repo_guard.assert_inside_repo(external)

    def test_bypass_scope_rejects_relative_or_missing_roots(self):
        with pytest.raises(ValueError, match="absolute directory"):
            with repo_guard.bypass_guard([Path("relative")]):
                pass

        with pytest.raises(ValueError, match="absolute directory"):
            with repo_guard.bypass_guard([PROJECT_ROOT.parent / "missing-root"]):
                pass


class TestTmpPath:
    def test_remains_repo_local_during_bypass_scope(self):
        with repo_guard.bypass_guard([PROJECT_ROOT.parent]):
            with pytest.raises(ValueError, match="escapes the ./tmp/ directory"):
                repo_guard.tmp_path("../../etc/passwd")

    def test_returns_path_under_tmp(self):
        result = repo_guard.tmp_path("test-file")
        assert str(result).startswith(str(PROJECT_ROOT / "tmp"))
        assert "test-file" in str(result)

    def test_does_not_create_directory(self):
        parent = PROJECT_ROOT / "tmp" / "repo-guard-uncreated"
        assert not parent.exists()
        try:
            repo_guard.tmp_path("repo-guard-uncreated/nested")
            assert not parent.exists()
        finally:
            if parent.exists():
                parent.rmdir()

    def test_raises_on_escaping_name(self):
        with pytest.raises(ValueError, match="escapes the ./tmp/ directory"):
            repo_guard.tmp_path("../../etc/passwd")

    def test_rejects_sibling_prefix_escape(self):
        with pytest.raises(ValueError, match="escapes the ./tmp/ directory"):
            repo_guard.tmp_path("../tmp-evil")

    def test_rejects_symlink_escape(self):
        link = PROJECT_ROOT / "tmp" / "repo-guard-link"
        try:
            link.symlink_to(PROJECT_ROOT / "tmp-evil", target_is_directory=True)
            with pytest.raises(ValueError, match="escapes the ./tmp/ directory"):
                repo_guard.tmp_path("repo-guard-link")
        finally:
            if link.is_symlink():
                link.unlink()


class TestRepoRoot:
    def test_returns_existing_directory(self):
        root = repo_guard.repo_root()
        assert root.exists()
        assert root.is_dir()

    def test_contains_dot_agents(self):
        root = repo_guard.repo_root()
        assert (root / ".agents").exists()

    def test_rejects_unverified_root(self, monkeypatch):
        monkeypatch.setattr(
            repo_guard,
            "__file__",
            str(PROJECT_ROOT / "tmp" / "no-repository" / ".agents" / "scripts" / "repo_guard.py"),
        )
        monkeypatch.setattr(repo_guard, "_ROOT", None)

        with pytest.raises(RuntimeError, match="repository root"):
            repo_guard.repo_root()


class TestAgentWorkspace:
    def test_supported_agent_aliases_target_canonical_workspace(self):
        for alias in (".opencode", ".codex", ".claude", ".hermes"):
            path = PROJECT_ROOT / alias
            assert path.is_symlink(), f"{alias} must be a symlink"
            assert path.readlink() == Path(".agents")

    def test_local_agent_artifacts_are_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".agents/local/example-artifact"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        assert result.returncode == 0
