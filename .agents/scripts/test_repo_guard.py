"""Tests for repo_guard.py — repo-boundary and temp-path enforcement."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
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
            repo_guard.assert_inside_repo("/tmp")

    def test_rejects_symlink_escaping(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = PROJECT_ROOT / "tmp" / "escape-link"
        try:
            link.symlink_to(outside, target_is_directory=True)
            with pytest.raises(ValueError, match="escapes the repository root"):
                repo_guard.assert_inside_repo(link)
        finally:
            if link.exists():
                link.unlink()

    def test_rejects_path_with_dot_dot(self):
        malicious = PROJECT_ROOT / ".." / "etc"
        with pytest.raises(ValueError, match="escapes the repository root"):
            repo_guard.assert_inside_repo(malicious)


class TestTmpPath:
    def test_returns_path_under_tmp(self):
        result = repo_guard.tmp_path("test-file")
        assert str(result).startswith(str(PROJECT_ROOT / "tmp"))
        assert "test-file" in str(result)

    def test_creates_directory(self):
        result = repo_guard.tmp_path("subdir/nested")
        assert result.parent.exists()
        result.parent.rmdir()

    def test_raises_on_escaping_name(self):
        with pytest.raises(ValueError, match="escapes the ./tmp/ directory"):
            repo_guard.tmp_path("../../etc/passwd")


class TestRepoRoot:
    def test_returns_existing_directory(self):
        root = repo_guard.repo_root()
        assert root.exists()
        assert root.is_dir()

    def test_contains_dot_agents(self):
        root = repo_guard.repo_root()
        assert (root / ".agents").exists()
