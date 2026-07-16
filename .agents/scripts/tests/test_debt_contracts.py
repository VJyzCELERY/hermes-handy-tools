"""Static contracts for debt policy and command documentation."""

from pathlib import Path


ROOT = Path(__file__).parents[3]


def read(path: str) -> str:
    """Read a repository contract file."""
    return (ROOT / path).read_text(encoding="utf-8")


def test_debt_command_resolves_before_confirmed_issue_creation_without_rewrite():
    content = read(".agents/commands/debt.md")

    for text in (
        "debt.py new",
        "debt.py list",
        "debt.py check",
        "debt.py resolve",
        "open and closed",
        "do not create a duplicate",
        "technical_debt.yml",
        "_common-github-ownership.md",
        "gh.py claim",
        "authenticated login",
        "confirmation",
        "create-issue",
        "Never rewrite the source marker",
    ):
        assert text in content, text


def test_agent_policy_requires_minimal_code_stable_debt_and_recorded_stubs():
    content = read(".agents/rules/001-agent-behavior.md")

    for text in (
        "standard library",
        "native platform",
        "minimum new code",
        "[DEBT][DEBT-XXXXXXXX]",
        "Multiple markers may share an ID",
        "Production stubs are prohibited",
        "Test doubles",
        "abstract/interface",
    ):
        assert text in content, text


def test_technical_debt_form_captures_identity_trigger_replacement_and_validation():
    content = read(".github/ISSUE_TEMPLATE/technical_debt.yml")

    for text in (
        "Debt ID",
        "Current Compromise",
        "Impact",
        "Cleanup Trigger",
        "Intended Replacement",
        "Acceptance Criteria",
        "Validation",
    ):
        assert text in content, text
