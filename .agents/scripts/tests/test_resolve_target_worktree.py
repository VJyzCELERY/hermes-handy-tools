"""Behavior tests for target-aware worktree resolution."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".agents" / "scripts" / "resolve-target-worktree.py"
sys.path.insert(0, str(SCRIPT.parent))


def resolver():
    """Load the resolver script without changing the interpreter path."""
    spec = importlib.util.spec_from_file_location("resolve_target_worktree", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    """Run Git in a disposable repository."""
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def target() -> dict:
    """Return canonical open PR metadata."""
    return {
        "kind": "pr",
        "repository": "acme/widgets",
        "number": 7,
        "url": "https://github.com/acme/widgets/pull/7",
        "title": "Ship resolver",
        "state": "OPEN",
        "branch": "feature/resolver",
        "base": "main",
        "head": "a" * 40,
    }


def issue_target() -> dict:
    """Return canonical open issue metadata."""
    return {
        "kind": "issue",
        "repository": "acme/widgets",
        "number": 7,
        "url": "https://github.com/acme/widgets/issues/7",
        "title": "Ship resolver",
        "state": "OPEN",
    }


def linked_pr(number: int = 7, body: str = "Closes #7") -> dict:
    """Return an open PR that closes one issue."""
    return {
        "number": number,
        "url": f"https://github.com/acme/widgets/pull/{number}",
        "title": "Ship resolver",
        "state": "OPEN",
        "headRefName": "feature/resolver",
        "baseRefName": "main",
        "headRefOid": "a" * 40,
        "body": body,
    }


def test_classify_prefers_an_open_pr_over_same_number_issue():
    module = resolver()

    def gh(*args: str) -> str:
        assert args[:3] == ("cmd", "--format", "json")
        return json.dumps(
            {
                "number": 7,
                "url": "https://github.com/acme/widgets/pull/7",
                "title": "Ship resolver",
                "state": "OPEN",
                "headRefName": "feature/resolver",
                "baseRefName": "main",
                "headRefOid": "a" * 40,
            }
        )

    resolved = module.classify_target("7", gh)

    assert resolved == target()


def test_classify_uses_an_open_issue_when_no_pr_exists():
    module = resolver()

    def gh(*args: str) -> str:
        if args[:5] == ("cmd", "--format", "json", "pr", "view"):
            raise module.TargetError("PR not found")
        if args[:5] == ("cmd", "--format", "json", "pr", "list"):
            return "[]"
        return json.dumps(
            {
                "number": 7,
                "url": "https://github.com/acme/widgets/issues/7",
                "title": "Ship resolver",
                "state": "OPEN",
            }
        )

    assert module.classify_target("7", gh) == {
        "kind": "issue",
        "repository": "acme/widgets",
        "number": 7,
        "url": "https://github.com/acme/widgets/issues/7",
        "title": "Ship resolver",
        "state": "OPEN",
    }


def test_classify_uses_an_open_issue_when_github_reports_missing_pr():
    module = resolver()

    def gh(*args: str) -> str:
        if args[:5] == ("cmd", "--format", "json", "pr", "view"):
            raise module.TargetError(
                "[FAIL] gh pr view 7 failed: GraphQL: Could not resolve to a "
                "PullRequest with the number of 7. (repository.pullRequest)"
            )
        if args[:5] == ("cmd", "--format", "json", "pr", "list"):
            return "[]"
        return json.dumps(
            {
                "number": 7,
                "url": "https://github.com/acme/widgets/issues/7",
                "title": "Ship resolver",
                "state": "OPEN",
            }
        )

    assert module.classify_target("7", gh) == issue_target()


def test_classify_preserves_unexpected_pr_lookup_failure():
    module = resolver()

    def gh(*_args: str) -> str:
        raise module.TargetError("gh authentication failed")

    with pytest.raises(module.TargetError, match="authentication failed"):
        module.classify_target("7", gh)


def test_classify_issue_uses_unique_open_linked_pr():
    module = resolver()

    def gh(*args: str) -> str:
        if args[:5] == ("cmd", "--format", "json", "pr", "view"):
            raise module.TargetError("PR not found")
        if args[:2] == ("fetch", "issue"):
            return json.dumps(issue_target())
        assert args[:5] == ("cmd", "--format", "json", "pr", "list")
        fields = args[args.index("--json") + 1]
        assert "body" in fields.split(",")
        assert "closingIssuesReferences" not in fields.split(",")
        return json.dumps([linked_pr()])

    assert module.classify_target("7", gh) == target()


def test_classify_issue_ignores_cross_repository_closing_reference():
    module = resolver()

    def gh(*args: str) -> str:
        if args[:5] == ("cmd", "--format", "json", "pr", "view"):
            raise module.TargetError("PR not found")
        if args[:2] == ("fetch", "issue"):
            return json.dumps(issue_target())
        return json.dumps([linked_pr(body="Fixes other/repo#7")])

    assert module.classify_target("7", gh) == issue_target()


def test_classify_issue_rejects_multiple_open_linked_prs():
    module = resolver()

    def gh(*args: str) -> str:
        if args[:5] == ("cmd", "--format", "json", "pr", "view"):
            raise module.TargetError("PR not found")
        if args[:2] == ("fetch", "issue"):
            return json.dumps(issue_target())
        return json.dumps([linked_pr(), linked_pr(8)])

    with pytest.raises(module.TargetError, match="multiple open PRs"):
        module.classify_target("7", gh)


def test_resolve_reuses_the_only_clean_matching_worktree(tmp_path):
    module = resolver()
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-m", "initial")
    worktree = tmp_path / ".worktrees" / "resolver"
    worktree.parent.mkdir()
    git(tmp_path, "worktree", "add", "-b", "feature/resolver", str(worktree))

    pr_target = target()
    pr_target["head"] = git(worktree, "rev-parse", "HEAD")
    result = module.resolve_target(tmp_path, pr_target)

    assert result["action"] == "reuse"
    assert result["path"] == str(worktree.resolve())


def test_resolve_ignores_pr_state_on_other_branches(tmp_path):
    module = resolver()
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-m", "initial")
    worktrees = []
    for name in ("one", "two"):
        worktree = tmp_path / ".worktrees" / name
        worktree.parent.mkdir(exist_ok=True)
        git(tmp_path, "worktree", "add", "-b", f"feature/{name}", str(worktree))
        state = worktree / ".agents/local/state/goals/acme_widgets_9.json"
        state.parent.mkdir(parents=True)
        state.write_text(
            json.dumps(
                {
                    "repository": "acme/widgets",
                    "prs": [{"number": 7, "head": "feature/resolver"}],
                }
            ),
            encoding="utf-8",
        )
        worktrees.append(worktree)

    assert module.resolve_target(tmp_path, target()) == {
        "action": "create",
        "branch": "feature/resolver",
    }


def test_resolve_rejects_ahead_matching_worktree(tmp_path):
    module = resolver()
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-m", "initial")
    worktree = tmp_path / ".worktrees" / "resolver"
    worktree.parent.mkdir()
    git(tmp_path, "worktree", "add", "-b", "feature/resolver", str(worktree))
    base = git(worktree, "rev-parse", "HEAD")
    git(tmp_path, "update-ref", "refs/remotes/origin/feature/resolver", base)
    (worktree / "tracked.txt").write_text("ahead\n", encoding="utf-8")
    git(worktree, "commit", "-am", "ahead")

    with pytest.raises(module.TargetError, match="ahead"):
        module.resolve_target(tmp_path, target())


def test_acquire_rejects_foreign_pr_before_worktree_mutation(tmp_path):
    module = resolver()
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "remote", "add", "origin", "https://github.com/current/repository.git")

    with pytest.raises(module.TargetError, match="foreign repository"):
        module.acquire_target(tmp_path, target())

    assert not (tmp_path / ".worktrees").exists()


def test_acquire_rejects_ahead_unchecked_out_local_branch(tmp_path):
    module = resolver()
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "remote", "add", "origin", "https://github.com/acme/widgets.git")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-m", "initial")
    branch = "feat/7-ship-resolver"
    git(tmp_path, "branch", branch)
    base = git(tmp_path, "rev-parse", branch)
    git(tmp_path, "update-ref", f"refs/remotes/origin/{branch}", base)
    git(tmp_path, "checkout", branch)
    (tmp_path / "tracked.txt").write_text("ahead\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "ahead")
    git(tmp_path, "checkout", "main")

    with pytest.raises(module.TargetError, match="ahead"):
        module.acquire_target(tmp_path, issue_target())

    assert not (tmp_path / ".worktrees").exists()


def test_refresh_pr_ref_fetches_before_comparing_head(monkeypatch, tmp_path):
    module = resolver()
    commands = []

    def git_command(root, *args):
        commands.append(args)
        if args[0] == "fetch":
            return ""
        assert args == ("rev-parse", "refs/remotes/origin/feature/resolver")
        assert commands[0][0] == "fetch"
        return "a" * 40

    monkeypatch.setattr(module, "_git", git_command)

    module._refresh_pr_ref(tmp_path, target())
