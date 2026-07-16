"""CLI tests for create-worktree.py."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".agents" / "scripts" / "create-worktree.py"
TMP = ROOT / "tmp"


class CreateWorktreeTests(unittest.TestCase):
    """Exercise the public command-line interface in disposable repositories."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(dir=TMP))
        self.repo = self.temp_dir / "repo"
        self.repo.mkdir()
        self.worktrees = self.repo / ".worktrees"
        self.worktrees.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-m", "initial")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def git(
        self, *args: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run Git in the disposable repository."""
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            check=True,
        )

    def command(
        self, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run the worktree command in the disposable repository."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_legacy_branch_and_base_create_isolated_worktree_config(self) -> None:
        worktree = self.worktrees / "legacy-worktree"

        result = self.command("feat/legacy", "main", "--path", str(worktree))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(worktree.is_dir())
        self.assertIn("BRANCH=feat/legacy", result.stdout)
        self.assertIn("BASE=main", result.stdout)
        self.assertEqual(
            self.git(
                "config", "--worktree", "--get", "worktree.base-branch", cwd=worktree
            ).stdout.strip(),
            "main",
        )
        shared_value = subprocess.run(
            ["git", "config", "--local", "--get", "worktree.base-branch"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(shared_value.returncode, 0)
        self.assertEqual(
            self.git("config", "--get", "extensions.worktreeConfig").stdout.strip(),
            "true",
        )

    def test_flags_and_dry_run_report_without_mutation(self) -> None:
        worktree = self.worktrees / "preview-worktree"

        result = self.command(
            "feat/preview", "--base", "main", "--path", str(worktree), "--dry-run"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BRANCH=feat/preview", result.stdout)
        self.assertIn(f"PATH={worktree.resolve()}", result.stdout)
        self.assertIn("BASE=main", result.stdout)
        self.assertIn("DRY_RUN=true", result.stdout)
        self.assertFalse(worktree.exists())
        branches = self.git("branch", "--format=%(refname:short)").stdout.splitlines()
        self.assertNotIn("feat/preview", branches)

    def test_lifecycle_root_places_worktree_under_source_worktree(self) -> None:
        source = self.repo / ".worktrees" / "source"
        self.git("worktree", "add", "-b", "feat/source", str(source), "main")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "feat/slice",
                "--base",
                "main",
                "--lifecycle-root",
                str(source),
            ],
            cwd=source,
            capture_output=True,
            text=True,
            check=False,
        )

        nested = source / ".worktrees" / "feat-slice"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(nested.is_dir())

    def test_lifecycle_root_must_be_an_exact_registered_worktree(self) -> None:
        unregistered = self.repo / ".worktrees" / "unregistered"
        unregistered.mkdir()

        result = self.command(
            "feat/slice", "--lifecycle-root", str(unregistered), "--dry-run"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("registered Git worktree", result.stderr)
        self.assertFalse((unregistered / ".worktrees" / "feat-slice").exists())

    def test_external_lifecycle_root_reports_validation_error_without_traceback(self) -> None:
        result = self.command(
            "feat/external-root",
            "--lifecycle-root",
            str(ROOT.parent),
            "--dry-run",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Worktree path must be inside", result.stderr)
        self.assertNotIn("UnboundLocalError", result.stderr)

    def test_attach_reuses_an_unchecked_out_existing_branch(self) -> None:
        worktree = self.worktrees / "attached-worktree"
        self.git("branch", "feat/attached")

        result = self.command(
            "feat/attached", "--base", "main", "--path", str(worktree), "--attach"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.git("branch", "--show-current", cwd=worktree).stdout.strip(),
            "feat/attached",
        )

    def test_invalid_git_branch_name_returns_diagnostic(self) -> None:
        result = self.command("feat//invalid", "--dry-run")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid branch name", result.stderr)
        self.assertIn("feat//invalid", result.stderr)

    def test_missing_base_returns_git_diagnostic(self) -> None:
        result = self.command("feat/missing-base", "--base", "does-not-exist")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does-not-exist", result.stderr)
        diagnostic = result.stderr.lower()
        self.assertTrue(
            "invalid reference" in diagnostic or "not a commit" in diagnostic
        )

    def test_path_outside_repository_worktrees_is_rejected_before_mutation(
        self,
    ) -> None:
        worktree = self.repo / "outside-worktrees"

        result = self.command("feat/outside", "--path", str(worktree))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".worktrees", result.stderr)
        self.assertFalse(worktree.exists())
        branches = self.git("branch", "--format=%(refname:short)").stdout.splitlines()
        self.assertNotIn("feat/outside", branches)
        extension = subprocess.run(
            ["git", "config", "--get", "extensions.worktreeConfig"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(extension.returncode, 0)

    def test_bypass_guard_allows_external_path_preview(self) -> None:
        external = ROOT.parent / "external-worktree-preview"

        result = self.command(
            "feat/external",
            "--path",
            str(external),
            "--bypass-guard",
            str(ROOT.parent),
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"PATH={external.resolve()}", result.stdout)
        self.assertFalse(external.exists())

    def test_bypass_guard_creates_external_worktree(self) -> None:
        external = ROOT.parent / f"external-worktree-{self.temp_dir.name}"
        try:
            result = self.command(
                "feat/external-created",
                "--base",
                "main",
                "--path",
                str(external),
                "--bypass-guard",
                str(ROOT.parent),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(external.is_dir())
        finally:
            if external.exists():
                self.git("worktree", "remove", "--force", str(external))

    def test_bypass_guard_keeps_internal_worktree_placement_restriction(self) -> None:
        outside_worktrees = self.repo / "outside-worktrees"

        result = self.command(
            "feat/internal",
            "--path",
            str(outside_worktrees),
            "--bypass-guard",
            str(ROOT.parent),
            "--dry-run",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".worktrees", result.stderr)
        self.assertFalse(outside_worktrees.exists())

    def test_worktree_config_failure_returns_nonzero_with_diagnostic(self) -> None:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        bin_dir = self.temp_dir / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "config" ] && [ "$2" = "--worktree" ]; then\n'
            '  echo "simulated config failure" >&2\n'
            "  exit 9\n"
            "fi\n"
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

        result = self.command(
            "feat/config-failure",
            "--path",
            str(self.worktrees / "config-failure-worktree"),
            env=env,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulated config failure", result.stderr)
        self.assertFalse((self.worktrees / "config-failure-worktree").exists())
        branches = self.git("branch", "--format=%(refname:short)").stdout.splitlines()
        self.assertNotIn("feat/config-failure", branches)

    def test_worktree_add_failure_restores_absent_extension(self) -> None:
        result = self.command("feat/failure", "--base", "does-not-exist")

        self.assertNotEqual(result.returncode, 0)
        extension = subprocess.run(
            ["git", "config", "--get", "extensions.worktreeConfig"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(extension.returncode, 0)


if __name__ == "__main__":
    unittest.main()
