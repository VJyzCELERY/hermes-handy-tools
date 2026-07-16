"""Integration tests for branch lifecycle commands."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import branch as branch_script


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".agents/scripts/branch.py"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git in a disposable repository."""
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=check
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a source branch with two commits."""
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "file.txt").write_text("base\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-m", "base")
    git(path, "switch", "-c", "feature/source")
    for number in (1, 2):
        with (path / "file.txt").open("a", encoding="utf-8") as stream:
            stream.write(f"change {number}\n")
        git(path, "add", ".")
        git(path, "commit", "-m", f"change {number}")
    return path


def command(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run branch.py inside a disposable repository."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def test_parser_accepts_bypass_guard_after_subcommand():
    args = branch_script.parse_args(
        ["breakdown", "--bypass-guard", str(ROOT)]
    )

    assert args.bypass_guard == [ROOT]


def test_parser_preserves_bypass_roots_on_both_sides_of_subcommand():
    first = ROOT
    second = ROOT.parent
    args = branch_script.parse_args(
        [
            "--bypass-guard",
            str(first),
            "breakdown",
            "--bypass-guard",
            str(second),
        ]
    )

    assert args.bypass_guard == [first, second]


def breakdown_plan(repo: Path) -> dict:
    """Create and return a two-slice breakdown plan."""
    result = command(
        repo,
        "breakdown",
        "--base",
        "main",
        "--lifecycle-id",
        "issue-42",
        "--issue-id",
        "42",
        "--slice",
        "feature/one=1",
        "--slice",
        "feature/source=1",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_breakdown_requires_approved_exact_plan(repo: Path):
    plan = breakdown_plan(repo)
    plan_path = repo / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    result = command(repo, "breakdown", "--apply", str(plan_path))

    assert result.returncode != 0
    assert "approved" in result.stderr.lower()


def test_breakdown_plan_contains_review_and_exact_boundary_metadata(repo: Path):
    plan = breakdown_plan(repo)

    assert plan["issue_id"] == "42"
    assert plan["base_head"] == git(repo, "rev-parse", "main").stdout.strip()
    assert plan["diff_summary"]["changed_files"] == 1
    assert plan["slices"][-1]["branch"] == "feature/source"
    for item in plan["slices"]:
        assert item["purpose"]
        assert item["paths"] == ["file.txt"]
        assert item["rationale"]
        assert item["validation"]["status"] == "deferred"
        assert item["review_disposition"] == "required"
        assert item["boundary"] == {
            "first": item["commits"][0],
            "last": item["commits"][-1],
            "count": len(item["commits"]),
        }


def test_breakdown_rejects_merge_history(repo: Path):
    git(repo, "switch", "-c", "side", "main")
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    git(repo, "add", "side.txt")
    git(repo, "commit", "-m", "side")
    git(repo, "switch", "feature/source")
    git(repo, "merge", "--no-ff", "side", "-m", "merge side")

    result = command(
        repo,
        "breakdown",
        "--base",
        "main",
        "--lifecycle-id",
        "issue-42",
        "--issue-id",
        "42",
        "--slice",
        "feature/one=2",
        "--slice",
        "feature/source=2",
    )

    assert result.returncode != 0
    assert "linear" in result.stderr.lower()


def test_breakdown_applies_clean_plan_and_preserves_tree(repo: Path):
    original_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    plan = breakdown_plan(repo)
    plan["approved"] = True
    plan_path = repo / ".agents/local/state/plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    result = command(repo, "breakdown", "--apply", str(plan_path), "--json")

    assert result.returncode == 0, result.stderr
    assert git(repo, "rev-parse", "HEAD^{tree}").stdout.strip() == original_tree
    assert git(repo, "branch", "--list", "backup/feature_source-*").stdout.strip()
    manifest = json.loads(
        (repo / ".agents/local/state/lifecycles/issue-42.json").read_text()
    )
    assert [item["branch"] for item in manifest["slices"]] == [
        "feature/one",
        "feature/source",
    ]
    assert [item["order"] for item in manifest["slices"]] == [1, 2]


def test_breakdown_rejects_dirty_or_stale_source(repo: Path):
    plan = breakdown_plan(repo)
    plan["approved"] = True
    plan_path = repo / ".agents/local/state/plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    (repo / "file.txt").write_text("dirty", encoding="utf-8")

    result = command(repo, "breakdown", "--apply", str(plan_path))

    assert result.returncode != 0
    assert "clean" in result.stderr.lower()
    assert not git(repo, "branch", "--list", "backup/*").stdout.strip()


def applied_lifecycle(repo: Path) -> None:
    """Apply the common breakdown fixture."""
    plan = breakdown_plan(repo)
    plan["approved"] = True
    path = repo / ".agents/local/state/plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan), encoding="utf-8")
    result = command(repo, "breakdown", "--apply", str(path))
    assert result.returncode == 0, result.stderr


def test_stack_previews_then_creates_cumulative_nested_worktrees(repo: Path):
    applied_lifecycle(repo)

    preview = command(repo, "stack", "issue-42", "--json")
    assert preview.returncode == 0, preview.stderr
    assert not (repo / ".worktrees/issue-42").exists()

    result = command(repo, "stack", "issue-42", "--apply", "--json")

    assert result.returncode == 0, result.stderr
    for name in ("feature-one",):
        worktree = repo / ".worktrees" / name
        assert worktree.is_dir()
        state = json.loads((worktree / ".agents/local/state/branch.json").read_text())
        assert "slices" not in state
        assert set(state) == {
            "version",
            "lifecycle_id",
            "branch",
            "source_worktree",
            "worktree",
        }
    assert not (repo / ".worktrees/feature-source").exists()
    assert git(repo, "branch", "--show-current").stdout.strip() == "feature/source"


def test_stack_rolls_back_only_new_resources_on_failure(repo: Path):
    applied_lifecycle(repo)
    git(repo, "branch", "feature/one")

    result = command(repo, "stack", "issue-42", "--apply")

    assert result.returncode != 0
    assert not (repo / ".worktrees/feature-one").exists()
    assert git(repo, "branch", "--list", "feature/one").stdout.strip()


@pytest.mark.parametrize("drift", ["head", "tree"])
def test_stack_apply_rejects_stale_source_before_creating_resources(
    repo: Path, drift: str
):
    applied_lifecycle(repo)
    manifest_path = repo / ".agents/local/state/lifecycles/issue-42.json"
    if drift == "head":
        (repo / "file.txt").write_text("replacement\n", encoding="utf-8")
        git(repo, "add", "file.txt")
        git(repo, "commit", "-m", "source drift")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_tree"] = "0" * 40
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = command(repo, "stack", "issue-42", "--apply")

    assert result.returncode != 0
    assert "source" in result.stderr.lower()
    assert not (repo / ".worktrees/feature-one").exists()
    assert not git(repo, "branch", "--list", "feature/one").stdout.strip()


def test_refresh_classifies_and_never_rebases_without_explicit_flag(repo: Path):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    before = git(repo, "rev-parse", "feature/one").stdout.strip()
    git(repo, "switch", "main")
    (repo / "base.txt").write_text("new base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "advance base")
    git(repo, "switch", "feature/source")

    result = command(repo, "refresh", "issue-42", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["classification"] == "stale-base"
    assert payload["affected"] == ["feature/one", "feature/source"]
    assert git(repo, "rev-parse", "feature/one").stdout.strip() == before
    assert "push" not in result.stdout.lower()


def test_refresh_detects_local_pointer_drift_without_upstream(repo: Path):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    git(repo, "-C", str(repo / ".worktrees/feature-one"), "reset", "--hard", "HEAD^")

    result = command(repo, "refresh", "issue-42", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["classification"] == "local-drift"
    assert payload["branches"]["feature/one"] == "local-drift"


def test_refresh_blocking_sync_status_outranks_stale_base(repo: Path):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    git(repo, "config", "branch.feature/one.remote", "origin")
    git(repo, "config", "branch.feature/one.merge", "refs/heads/feature/one")
    git(repo, "switch", "main")
    (repo / "base.txt").write_text("new base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "advance base")
    git(repo, "switch", "feature/source")

    result = command(repo, "refresh", "issue-42", "--apply-rebase", "--json")

    assert result.returncode != 0
    assert "missing-remote" in result.stderr


@pytest.mark.parametrize(
    "observations",
    [
        [
            {
                "number": 1,
                "state": "CLOSED",
                "headRefName": "feature/one",
                "baseRefName": "main",
            }
        ],
        [
            {
                "number": 1,
                "state": "MERGED",
                "headRefName": "feature/one",
                "baseRefName": "main",
            }
        ],
        [{"number": 1, "state": "OPEN", "headRefName": "wrong", "baseRefName": "main"}],
        [
            {
                "number": 1,
                "state": "OPEN",
                "headRefName": "feature/one",
                "baseRefName": "wrong",
            }
        ],
        [
            {
                "number": 1,
                "state": "OPEN",
                "headRefName": "feature/one",
                "baseRefName": "main",
            },
            {
                "number": 2,
                "state": "OPEN",
                "headRefName": "feature/one",
                "baseRefName": "main",
            },
        ],
    ],
)
def test_refresh_blocks_unsafe_authoritative_pr_observations(repo: Path, observations):
    applied_lifecycle(repo)
    path = repo / ".agents/local/state/pr-observations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"feature/one": observations, "feature/source": []}),
        encoding="utf-8",
    )

    result = command(
        repo, "refresh", "issue-42", "--pr-observations", str(path), "--json"
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["classification"] == "blocked"


@pytest.mark.parametrize(
    "observations",
    [
        {"feature/one": []},
        {"feature/one": [], "feature/source": [], "feature/extra": []},
        {"feature/one": {}, "feature/source": []},
        {"feature/one": [{"number": 1}], "feature/source": []},
    ],
)
def test_refresh_rejects_inexact_or_malformed_pr_observations(repo: Path, observations):
    applied_lifecycle(repo)
    path = repo / ".agents/local/state/pr-observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")

    result = command(
        repo, "refresh", "issue-42", "--pr-observations", str(path), "--json"
    )

    assert result.returncode != 0
    assert "observations" in result.stderr.lower()


def test_mutation_rejects_unrelated_untracked_but_allows_local_state(repo: Path):
    plan = breakdown_plan(repo)
    plan["approved"] = True
    plan_path = repo / ".agents/local/state/plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    (repo / "unrelated.txt").write_text("untracked\n", encoding="utf-8")

    result = command(repo, "breakdown", "--apply", str(plan_path))

    assert result.returncode != 0
    assert "clean" in result.stderr.lower()


def test_refresh_classifies_unrelated_untracked_file_as_blocked(repo: Path):
    applied_lifecycle(repo)
    (repo / "unrelated.txt").write_text("untracked\n", encoding="utf-8")

    result = command(repo, "refresh", "issue-42", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["classification"] == "blocked"


def test_refresh_rebases_suffix_only_with_explicit_flag(repo: Path):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    old = git(repo, "rev-parse", "feature/one").stdout.strip()
    git(repo, "switch", "main")
    (repo / "base.txt").write_text("new base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "advance base")
    new_base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "switch", "feature/source")

    result = command(repo, "refresh", "issue-42", "--apply-rebase", "--json")

    assert result.returncode == 0, result.stderr
    assert git(repo, "merge-base", "feature/one", "main").stdout.strip() == new_base
    assert git(repo, "rev-parse", "feature/one").stdout.strip() != old
    assert git(repo, "branch", "--show-current").stdout.strip() == "feature/source"
    assert (
        git(repo, "merge-base", "feature/source", "feature/one").stdout.strip()
        == git(repo, "rev-parse", "feature/one").stdout.strip()
    )
    manifest = json.loads(
        (repo / ".agents/local/state/lifecycles/issue-42.json").read_text()
    )
    assert manifest["base_head"] == new_base


@pytest.mark.parametrize("checkout", ["main", "detached"])
def test_refresh_apply_rebase_requires_checked_out_source_before_mutation(
    repo: Path, checkout: str
):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    git(repo, "switch", "main")
    (repo / "base.txt").write_text("new base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "advance base")
    if checkout == "detached":
        git(repo, "switch", "--detach")
    tips = {
        branch: git(repo, "rev-parse", branch).stdout.strip()
        for branch in ("feature/one", "feature/source")
    }

    result = command(repo, "refresh", "issue-42", "--apply-rebase", "--json")

    assert result.returncode != 0
    assert "source branch" in result.stderr.lower()
    for branch, tip in tips.items():
        assert git(repo, "rev-parse", branch).stdout.strip() == tip


@pytest.mark.parametrize("failure", ["empty", "write"])
def test_refresh_post_rebase_failure_restores_tips_and_manifest(
    repo: Path, monkeypatch, failure: str
):
    applied_lifecycle(repo)
    command(repo, "stack", "issue-42", "--apply")
    tips = {
        branch: git(repo, "rev-parse", branch).stdout.strip()
        for branch in ("feature/one", "feature/source")
    }
    manifest_path = repo / ".agents/local/state/lifecycles/issue-42.json"
    manifest = manifest_path.read_text(encoding="utf-8")
    git(repo, "switch", "main")
    (repo / "base.txt").write_text("new base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "advance base")
    git(repo, "switch", "feature/source")

    if failure == "empty":
        real_git = branch_script.git

        def empty_slice(*args, cwd):
            if args[:2] == ("rev-list", "--reverse") and args[-1].endswith(
                "..feature/one"
            ):
                return ""
            return real_git(*args, cwd=cwd)

        monkeypatch.setattr(branch_script, "git", empty_slice)
    else:

        def fail_write(*_args, **_kwargs):
            raise OSError("state write failed")

        monkeypatch.setattr(branch_script.branch_state, "write_lifecycle", fail_write)

    args = argparse.Namespace(
        lifecycle_id="issue-42",
        fetch=False,
        apply_rebase=True,
        pr_observations=None,
    )
    with pytest.raises((RuntimeError, OSError)):
        branch_script.refresh(args, repo)

    assert manifest_path.read_text(encoding="utf-8") == manifest
    for branch, tip in tips.items():
        assert git(repo, "rev-parse", branch).stdout.strip() == tip
