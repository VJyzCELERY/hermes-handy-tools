"""Contract tests for generated-document and subproject templates."""

import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[3]
TEMPLATES = ROOT / ".agents" / "templates"
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))


def test_document_templates_are_output_schemas_only():
    names = (
        "spec.md",
        "design.md",
        "implementation-plan.md",
        "PR-body.md",
        "skill.md",
    )
    forbidden = (
        "<!--",
        "do not leave",
        "must not be implemented",
        "run `/implement`",
        "generated from spec.md",
        "if no special",
        "this ensures the developer",
        "if your harness",
    )

    for name in names:
        content = (TEMPLATES / name).read_text().lower()
        assert not any(text in content for text in forbidden), name


def test_spec_and_design_keep_rule_007_sections():
    spec = (TEMPLATES / "spec.md").read_text()
    design = (TEMPLATES / "design.md").read_text()

    for heading in (
        "## Problem Statement",
        "## User Scenarios & Testing",
        "## Requirements",
        "## Success Criteria",
        "## Testing Plan",
    ):
        assert heading in spec
    for heading in (
        "## Overview",
        "## Architecture",
        "## Data Model",
        "## API / Interface Contracts",
        "## Implementation Phases",
        "## Technical Decisions",
        "## Risks & Mitigations",
    ):
        assert heading in design


def test_task_template_keeps_consumed_stable_ids_without_other_comments():
    task = (TEMPLATES / "task.md").read_text()
    comments = re.findall(r"<!--.*?-->", task)

    assert comments
    assert all(re.fullmatch(r"<!-- id: \d+ -->", comment) for comment in comments)
    assert len(comments) == len(set(comments))


def test_pr_template_keeps_exact_headings_and_neutral_commands():
    import gh

    body = (TEMPLATES / "PR-body.md").read_text()
    headings = re.findall(r"^## .+$", body, flags=re.MULTILINE)
    testing = body.split("## How to Test", 1)[1].split("## Review Notes", 1)[0]

    assert headings == [
        "## Summary",
        "## How to Test",
        "## Review Notes",
        "## Related Issues",
    ]
    assert not re.search(r"\b(?:uv|pytest|ruff|mypy|npm|cargo)\b", testing)
    assert any("placeholder" in error.lower() for error in gh.validate_pr_body(body))
    assert len(re.findall(r"\[[^\]]+\]", body)) == len(
        gh.TEMPLATE_PLACEHOLDER_RE.findall(body)
    )


def test_issue_centered_templates_carry_primary_issue_and_pr_linkage():
    for name in ("spec.md", "implementation-plan.md", "PR-body.md"):
        assert "Primary Issue" in (TEMPLATES / name).read_text(), name

    body = (TEMPLATES / "PR-body.md").read_text()
    assert "Closes #N" in body
    assert "Refs #N" in body
    assert "final" in body.lower()
    assert "stack" in body.lower()


def test_review_template_remote_feedback_is_machine_readable():
    import review_common

    content = (TEMPLATES / "REVIEW-template.md").read_text()
    assert review_common.parse_remote_feedback(content) == "UNLINKED"


def test_issue_forms_are_project_generic():
    forms = ROOT / ".github" / "ISSUE_TEMPLATE"
    content = "\n".join(path.read_text().lower() for path in forms.glob("*.yml"))

    assert "tinycua" not in content
    assert "sdk" not in content


def test_subproject_agent_files_only_inherit_root_contract():
    for kind in ("subproject-generic", "subproject-python"):
        content = (TEMPLATES / "subproject-template" / kind / "AGENTS.md").read_text()
        assert content == (
            "# Subproject Contract\n\n"
            "The repository root `AGENTS.md` applies to this subproject. "
            "Read `../../AGENTS.md` before working here.\n"
        )


def test_subproject_readmes_only_advertise_present_scaffold_paths():
    for kind in ("subproject-generic", "subproject-python"):
        template = TEMPLATES / "subproject-template" / kind
        readme = (template / "README.md").read_text()
        assert "specs/README.md" not in readme
        assert "docs/agents" not in readme
        assert "docs/examples" not in readme
        for path in re.findall(r"`([^`\n]+)`", readme):
            if path.startswith(("src/", "make ", "<")):
                continue
            advertised = template / path.rstrip("/")
            assert advertised.exists(), (kind, path)
            assert advertised.is_file() or any(advertised.rglob("*")), (kind, path)


def test_python_scaffold_matches_canonical_tooling_rules():
    template = TEMPLATES / "subproject-template" / "subproject-python"
    config = tomllib.loads((template / "pyproject.toml").read_text())
    lint = config["tool"]["ruff"]["lint"]

    assert config["tool"]["ruff"]["line-length"] == 88
    assert lint["select"] == [
        "E",
        "F",
        "I",
        "N",
        "W",
        "D",
        "UP",
        "B",
        "SIM",
        "ARG",
        "LOG",
        "PT",
        "S",
        "PTH",
        "RUF",
        "C901",
    ]
    assert lint["mccabe"]["max-complexity"] == 10
    assert lint["flake8-tidy-imports"]["ban-relative-imports"] == "all"
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert "--cov" in config["tool"]["pytest"]["ini_options"]["addopts"]

    dependencies = set(config["dependency-groups"]["dev"])
    makefile = (template / "Makefile").read_text()
    invoked_as = {
        "pytest": "pytest",
        "pytest-cov": "--cov",
        "ruff": "ruff",
        "radon": "radon",
    }
    for dependency, command_token in invoked_as.items():
        assert dependency in dependencies
        assert command_token in makefile
