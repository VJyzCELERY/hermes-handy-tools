"""Static contracts for issue-centered command documentation."""

import re
from pathlib import Path


ROOT = Path(__file__).parents[3]
COMMANDS = ROOT / ".agents" / "commands"
ISSUE_FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"


def command(name: str) -> str:
    """Read one command contract."""
    return (COMMANDS / name).read_text(encoding="utf-8")


def test_issue_contract_guards_selection_and_remote_creation():
    content = command("issue.md")

    for text in (
        "existing",
        "create",
        "duplicate",
        ".github/ISSUE_TEMPLATE/",
        "readiness",
        "open",
        "roadmap",
        "confirm",
        "create-issue",
        "unclaimed",
    ):
        assert text in content, text

    for text in ("_common-github-ownership.md", "gh.py claim", "workflow_state.py"):
        assert text not in content, text


def test_remote_specs_contracts_link_and_exclude_specs_issues():
    assert "`spec`-labelled" in command("issue.md")
    assert "set-specs" in command("plan.md")
    assert "links the primary issue" in command("plan.md")
    assert "remote references" in command("implement.md")
    assert "Specs: #<number>" in command("create-pr.md")
    assert "spec`-labelled" in command("goal.md")
    assert "Specs Issue" in (ROOT / ".agents/templates/PR-body.md").read_text()


def test_remote_pr_bodies_use_only_validated_current_specs_documents():
    content = command("create-pr.md")

    assert "workflow_state.specs.documents" in content
    assert "validated" in content
    assert "local profile" in content


def test_plan_contract_previews_and_confirms_remote_specs_mutations():
    content = command("plan.md")

    for text in (
        "Preview the exact remote Specs mutations",
        "create the `spec` label",
        "create or reuse the Specs issue",
        "link the primary issue",
        "append up to four document comments",
        "update the Specs revision index",
        "fresh remote-write confirmation",
        "inherited `--auto`",
    ):
        assert text in content, text


def test_implementation_issue_forms_capture_acceptance_and_validation():
    for name in ("bug_report.yml", "feature_request.yml"):
        content = (ISSUE_FORMS / name).read_text(encoding="utf-8")
        assert "Acceptance Criteria" in content, name
        assert "Validation" in content, name


def test_plan_and_implement_resolve_issue_state_and_artifacts():
    for name in ("plan.md", "implement.md"):
        content = command(name)
        assert "OWNER/REPO#NUMBER" in content
        assert "workflow_state.py show" in content
        assert "state artifacts" in content.lower()
        assert "workflow_state.py resolve-active --format json" in content

    assert "workflow_state.py set-artifacts" in command("plan.md")
    implement = command("implement.md")
    for text in ("complete plan artifacts", "commit", "push", "separate sibling PR delivery"):
        assert text in implement, text


def test_goal_and_implement_initialize_acquired_target_state_before_reading_it():
    for name in ("goal.md", "implement.md"):
        content = command(name)

        acquire = content.index("resolve-target-worktree.py")
        issue_init = content.index("workflow_state.py init OWNER/REPO#NUMBER")
        issue_show = content.index("workflow_state.py show OWNER/REPO#NUMBER")
        pr_init = content.index("workflow_state.py init-pr OWNER/REPO!NUMBER")
        plan_head = content.index(
            "workflow_state.py validate-plan-head OWNER/REPO!NUMBER"
        )

        assert acquire < issue_init < issue_show, name
        assert acquire < pr_init < plan_head, name
        assert "otherwise run `uv run python .agents/scripts/workflow_state.py show" not in content


def test_create_pr_contract_owns_single_and_stack_linkage_and_permissions():
    content = command("create-pr.md")

    for text in (
        "single",
        "full stack",
        "create or update",
        "Closes",
        "final PR",
        "Refs",
        "earlier",
        "Preview",
        "push",
        "separate",
        "remote write",
        "workflow_state.py set-pr",
        "workflow_state.py resolve-active --format json",
        "--draft",
        "gh.py claim",
        "preserve",
    ):
        assert text in content, text


def test_create_pr_contract_rejects_spec_issues():
    content = command("create-pr.md")

    assert "non-`spec`-labelled" in content
    assert content.index("non-`spec`-labelled") < content.index(
        "Prepare one filled PR body"
    )


def test_goal_contract_is_resumable_autonomous_and_merge_ready():
    content = command("goal.md")

    for text in (
        "exactly one",
        "workflow_state.py show",
        "resume",
        "@.agents/commands/implement.md",
        "one complete run authorization",
        "baseline review",
        "mechanically clear",
        "@.agents/commands/review-implement.md",
        "@.agents/commands/review-validate.md",
        "goal_delivered",
        "clean merge-ready PR",
        "workflow_state.py resolve-active --format json",
        "gh.py claim",
        "issue body",
        "PR body",
    ):
        assert text in content, text

    assert "<type>/<issue-number>-<lower-kebab-slug>" in content
    assert "use the acquired returned worktree" in content
    assert "at most one" not in content


def test_goal_contract_retries_only_environment_failures_and_blocks_decisions():
    content = command("goal.md")

    for text in (
        "record-environment-failure",
        "reset-environment-retry",
        "five consecutive identical",
        "scope expansion",
        "ambiguity",
        "security or permission gate",
        "conflict requiring human choice",
        "safe resume point",
        "non-mechanical",
        "invalid delegated evidence",
    ):
        assert text in content, text


def test_goal_contract_delivers_each_mechanical_cycle_and_readies_without_merging():
    content = command("goal.md")

    for text in (
        "until no OPEN findings remain",
        "fresh sibling",
        "PR delivery",
        "gh.py cmd --format json pr ready <pr-number>",
        "isDraft",
        "false",
        "administrator-policy override",
    ):
        assert text in content, text

    assert content.index("pr ready <pr-number>") < content.index("pr merge <pr-number>")
    assert "--auto-merge" in content


def test_target_aware_contracts_acquire_the_source_worktree_from_primary():
    commands = (
        "plan.md",
        "implement.md",
        "goal.md",
        "create-pr.md",
        "begin-worktree.md",
    )

    for name in commands:
        content = command(name)
        assert "resolve-target-worktree.py" in content, name
        assert "primary checkout" in content, name
        assert "returned worktree" in content, name

    review_context = command("_common-review-context.md")
    assert "resolve-target-worktree.py" in review_context
    assert "primary checkout" in review_context
    assert "returned worktree" in review_context

    for name in ("review-fetch.md", "review-post.md", "review-refresh.md", "review-update.md"):
        assert "returned worktree" in command(name), name


def test_goal_delegates_implementation_pr_delivery_then_review():
    content = command("goal.md")

    assert "@.agents/commands/implement.md" in content
    assert "@.agents/commands/create-pr.md" in content
    assert "@.agents/commands/review.md" in content


def test_goal_directly_dispatches_each_delivery_phase_without_nested_delegation():
    goal = command("goal.md")
    implement = command("implement.md")

    for command_name in (
        "plan.md",
        "implement.md",
        "create-pr.md",
        "review.md",
        "review-implement.md",
        "review-validate.md",
    ):
        assert f"@.agents/commands/{command_name}" in goal, command_name

    assert "delegate `/plan`" not in implement
    assert "delegate `/create-pr`" not in implement


def test_begin_workflow_is_replaced_by_goal():
    assert not (COMMANDS / "begin-workflow.md").exists()


def test_command_readme_is_the_exact_public_inventory():
    public = {
        path.stem
        for path in COMMANDS.glob("*.md")
        if path.name != "README.md" and not path.name.startswith("_")
    }
    mapped = re.findall(r"^\| `/([^`]+)` \|", command("README.md"), re.MULTILINE)

    assert len(mapped) == len(set(mapped))
    assert set(mapped) == public


def test_removed_commands_are_not_referenced_in_guidance():
    removed = (
        "begin-workflow",
        "review-report",
        "review-loop",
        "review-clarify",
        "review-verify",
    )
    paths = [ROOT / "AGENTS.md", ROOT / "PROJECT-GUIDELINES.md"]
    paths += list((ROOT / ".agents").glob("**/*.md"))

    for path in paths:
        content = path.read_text(encoding="utf-8")
        for name in removed:
            assert f"/{name}" not in content, (path, name)
            assert f"commands/{name}.md" not in content, (path, name)


def test_branch_commands_have_frontmatter_and_share_common_modules():
    branch_commands = ("branch-breakdown.md", "branch-refresh.md", "branch-stack.md")
    common_modules = tuple(COMMANDS.glob("_common-branch-*.md"))

    for name in branch_commands:
        content = command(name)
        assert content.startswith("---\n")
        assert re.search(r"^description: \S", content, re.MULTILINE)
    for module in common_modules:
        consumers = [name for name in branch_commands if module.name in command(name)]
        assert len(consumers) >= 2, (module.name, consumers)


def test_documented_workflow_state_calls_match_required_cli_arguments():
    create_pr = command("create-pr.md")

    assert (
        "workflow_state.py set-pr OWNER/REPO#NUMBER <number> --url <url> --head <head> --base <base> --format json"
        in create_pr
    )


def test_commands_document_exact_phase_boundaries_and_complete_plan_artifacts():
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER branched --status active --clear-pending-action --format json"
        in command("goal.md")
    )
    assert (
        "workflow_state.py set-artifacts OWNER/REPO#NUMBER --directory <directory> --spec <spec> --design <design> --plan <plan> --task <task> --format json"
        in command("plan.md")
    )
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER planned --status active --clear-pending-action --format json"
        in command("plan.md")
    )
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER implementing --status active --clear-pending-action --format json"
        in command("implement.md")
    )
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER implemented --status active --clear-pending-action --format json"
        in command("implement.md")
    )
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER pr_open --status active --clear-pending-action --format json"
        in command("create-pr.md")
    )
    assert (
        "workflow_state.py transition OWNER/REPO#NUMBER reviewing --status active --clear-pending-action --format json"
        in command("goal.md")
    )


def test_create_pr_and_issue_document_exact_gh_write_forms():
    create_pr = command("create-pr.md")
    assert "uv run python .agents/scripts/gh.py update title <pr> <title>" in create_pr
    assert (
        "uv run python .agents/scripts/gh.py update body <pr> <body-file>" in create_pr
    )
    issue = command("issue.md")
    assert "create-issue <title> ./tmp/issue-body.md --label <labels> --unclaimed --format json" in issue
    assert "--assignee" not in issue


def test_ownership_contract_is_shared_by_github_workflows():
    module = "_common-github-ownership.md"
    consumers = ("goal.md", "implement.md", "create-pr.md")

    for name in consumers:
        content = command(name)
        assert module in content, name
        assert "gh.py claim" in content, name

    common = command(module)
    assert "preserve existing assignees" in common
    assert "authenticated GitHub login" in common
    assert "issue and PR" in common


def test_implement_claims_resolved_issue_and_pr_context_before_source_mutation():
    content = command("implement.md")

    claim = content.index("gh.py claim")
    transition = content.index("workflow_state.py transition")
    assert claim < transition
    assert "issue body" in content
    assert "PR body" in content


def test_goal_delegates_the_current_review_command():
    content = command("goal.md")

    assert "@.agents/commands/review.md" in content
    assert "review-report" not in content


def test_goal_records_review_evidence_before_delivery():
    content = command("goal.md")
    set_review = content.index("workflow_state.py set-review")
    delivered = content.index(
        "workflow_state.py transition OWNER/REPO#NUMBER goal_delivered"
    )

    assert set_review < delivered
    assert "<canonical-report>" in content
    assert "<canonical-archive>" in content
    assert "--state <ACTIVE_OPEN|COMPLETE|CLEAN|ARCHIVED>" in content


def test_goal_requires_independent_delegated_phase_ownership():
    content = command("goal.md")

    required = (
        "orchestration-only",
        "fresh subagent A",
        "distinct fresh subagent B",
        "distinct fresh subagent C",
        "distinct fresh subagent D",
        "fresh subagent E",
        "directly resumes D by task identity",
        "fresh validator",
        "records the fallback",
        "fresh subagent F",
        "missing, failed, or malformed delegated result",
        "without advancing state",
        "parent-authored substitute work",
    )
    for text in required:
        assert text in content, text

    assert (
        content.index("fresh subagent A")
        < content.index("distinct fresh subagent B")
        < content.index("distinct fresh subagent C")
        < content.index("distinct fresh subagent D")
        < content.index("fresh subagent E")
        < content.index("directly resumes D by task identity")
        < content.index("fresh subagent F")
    )


def test_goal_requires_main_agent_sibling_dispatch_without_harness_dependencies():
    content = command("goal.md")

    required = (
        "Run `/goal` only in the main agent",
        "cannot establish that role",
        "directly dispatches sibling subagents",
        "directly dispatches fresh subagent A as a sibling",
        "directly dispatches distinct fresh subagent B as a sibling",
        "directly dispatches distinct fresh subagent C as a sibling",
        "directly dispatches distinct fresh subagent D as a sibling",
        "directly dispatching fresh subagent E as a sibling",
        "directly resumes D by task identity",
        "directly dispatches validation to a fresh validator sibling",
        "directly dispatches it to fresh subagent F as a sibling",
        "phase agents do not spawn agents",
        "nested-agent",
        "background-process",
        "polling",
        "harness-specific runner",
    )
    for text in required:
        assert text in content, text

    assert content.index("Run `/goal` only in the main agent") < content.index(
        "workflow_state.py init OWNER/REPO#NUMBER"
    )


def test_goal_contract_records_validated_per_goal_trace_events():
    content = command("goal.md")

    state_init = content.index("workflow_state.py init OWNER/REPO#NUMBER")
    trace_init = (
        "goal_trace.py init OWNER/REPO#NUMBER [--auto] [--commit] [--push] "
        "[--pr-create] [--pr-ready] [--merge] [--administrator-merge]"
    )
    pr_init = content.index("workflow_state.py init-pr OWNER/REPO!NUMBER")
    assert state_init < content.index(trace_init)
    assert pr_init < content.index(trace_init)
    assert content.count(trace_init) == 1

    for text in (
        "goal_trace.py validate OWNER/REPO#NUMBER",
        "goal_trace.py append-log OWNER/REPO#NUMBER",
        "goal_trace.py append-audit OWNER/REPO#NUMBER",
        "phase transitions",
        "delegation",
        "pause and resume",
        "block",
        "ready",
        "merge outcomes",
        "concise log",
        "detailed audit",
        "Never record secrets, raw command output",
        "Trace configuration is observability metadata, not authorization",
        "records current permission facts only and never grants permissions",
    ):
        assert text in content, text

    assert content.index("goal_trace.py validate OWNER/REPO#NUMBER") < content.index(
        "goal_trace.py append-log OWNER/REPO#NUMBER"
    )
