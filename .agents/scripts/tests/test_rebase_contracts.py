"""Static contracts for explicit rebase safety."""

from pathlib import Path


ROOT = Path(__file__).parents[3]


def read(path: str) -> str:
    """Read one repository contract."""
    return (ROOT / path).read_text(encoding="utf-8")


def test_normative_git_rule_owns_explicit_rebase_forms():
    content = read(".agents/rules/008-git-operations.md")

    assert "--onto <new-base> <old-base> <branch>" in content
    assert "--update-refs" in content
    assert "verified true linear stack" in content
    assert "git pull --rebase" in content


def test_rebase_consumers_load_normative_git_rule():
    for path in (
        ".agents/commands/rebase.md",
        ".agents/commands/branch-refresh.md",
        ".agents/commands/commit-cleanup.md",
        ".agents/skills/git/SKILL.md",
    ):
        assert "008-git-operations.md" in read(path), path

    assert "008-git-operations.md" in read("AGENTS.md")
    assert "008-git-operations.md" in read("PROJECT-GUIDELINES.md")


def test_rebase_command_documents_topology_specific_execution_and_verification():
    content = read(".agents/commands/rebase.md")

    assert "--onto <new-base> <old-base> <branch>" in content
    assert "--update-refs" in content
    assert "checked out in another worktree" in content
    assert "verify every affected ref" in content
