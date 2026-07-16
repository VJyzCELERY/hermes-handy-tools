"""Static contracts for command automation."""

import re
from pathlib import Path


ROOT = Path(__file__).parents[3]
COMMANDS = ROOT / ".agents" / "commands"


def _command(name: str) -> str:
    """Return one command document."""
    return (COMMANDS / name).read_text(encoding="utf-8")


def test_root_contract_applies_automation_to_every_public_command():
    public = {
        path.name
        for path in COMMANDS.glob("*.md")
        if path.name != "README.md" and not path.name.startswith("_")
    }
    readme = _command("README.md")
    contract = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Every public command accepts `--auto`" in contract
    assert "all commands in the current session" in contract
    assert all(f"`/{path.removesuffix('.md')}`" in readme for path in public)


def test_command_inventory_includes_session_automation():
    commands = set(re.findall(r"^\| `/([^`]+)` \|", _command("README.md"), re.MULTILINE))

    assert "auto" in commands


def test_goal_supports_one_shot_and_unattended_automation():
    content = _command("goal.md")

    for text in (
        "one complete run authorization",
        "--auto",
        "inherited authorization",
        "--auto-merge",
        "merge-ready PR",
        "pr ready <pr-number>",
        "isDraft",
    ):
        assert text in content, text

    assert "resolve-target-worktree.py" in content
    for command in ("implement.md", "review.md"):
        assert f"@.agents/commands/{command}" in content
    assert "pr merge <pr-number> --merge" in content
    assert content.index("pr ready <pr-number>") < content.index("pr merge <pr-number>")


def test_delivery_contracts_limit_inherited_goal_authorization_to_the_confirmed_batch():
    review_implement = _command("review-implement.md")
    create_pr = _command("create-pr.md")

    for content in (review_implement, create_pr):
        assert "inherited `/goal` authorization" in content
        assert "standalone" in content


def test_auto_defines_session_scope():
    auto = _command("auto.md")

    assert "all commands in the current session" in " ".join(auto.split())
