import builtins
import importlib.util
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).parent.parent / "check-agents-consistency.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("check_agents_consistency", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(checker)


@pytest.fixture
def workspace():
    path = ROOT / "tmp" / f"test-check-consistency-{uuid.uuid4().hex}"
    path.mkdir()
    yield path
    shutil.rmtree(path)


def test_cli_rejects_nonexistent_dir():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", "tmp/does-not-exist"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_check_raw_gh_detects_subprocess_list_literal(workspace):
    source = workspace / "caller.py"
    source.write_text(
        'import subprocess\nsubprocess.run(["gh", "pr", "view"], check=True)\n'
    )

    findings = checker.check_raw_gh([], [source])

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR
    assert findings[0][2] == 2


def test_check_raw_gh_detects_shared_wrapper_list_literal(workspace):
    source = workspace / "caller.py"
    source.write_text(
        'from cli_common import run_process\nrun_process(["gh", "pr", "view"])\n'
    )

    findings = checker.check_raw_gh([], [source])

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR
    assert findings[0][2] == 2


def test_check_raw_gh_ignores_non_subprocess_literals_and_gh_wrapper(workspace):
    prose = workspace / "example.py"
    prose.write_text('example = ["gh", "pr", "view"]\n')
    wrapper = workspace / "gh.py"
    wrapper.write_text(
        'import subprocess\nsubprocess.run(["gh", "pr", "view"], check=True)\n'
    )

    findings = checker.check_raw_gh([], [prose, wrapper])

    assert findings == []


def test_check_raw_gh_ignores_fixture_string_containing_wrapper_call(workspace):
    fixture = workspace / "test_fixture.py"
    fixture.write_text(
        'source.write_text(\'run_process(["gh", "pr", "view"])\\n\')\n'
    )

    assert checker.check_raw_gh([], [fixture]) == []


@pytest.mark.parametrize(
    "command",
    (
        "`git rebase main`",
        "`git pull --rebase`",
    ),
)
def test_check_implicit_rebase_rejects_markdown_commands(workspace, command):
    document = workspace / "instructions.md"
    document.write_text(f"Run {command}.\n")

    findings = checker.check_implicit_rebase([document], [])

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR


@pytest.mark.parametrize(
    "command",
    (
        "`git rebase --onto main old feature`",
        "`git rebase main --update-refs`",
        "`git rebase --abort`",
        "`git rebase --continue`",
    ),
)
def test_check_implicit_rebase_allows_explicit_and_control_markdown(
    workspace, command
):
    document = workspace / "instructions.md"
    document.write_text(f"Run {command}.\n")

    assert checker.check_implicit_rebase([document], []) == []


@pytest.mark.parametrize(
    "source",
    (
        'git("rebase", "main")\n',
        'run_process(["git", "rebase", "main"])\n',
        'run_process(["git", "pull", "--rebase"])\n',
    ),
)
def test_check_implicit_rebase_rejects_python_construction(workspace, source):
    script = workspace / "rebase.py"
    script.write_text(source)

    findings = checker.check_implicit_rebase([], [script])

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR


def test_check_implicit_rebase_allows_explicit_python_and_fixture_strings(workspace):
    explicit = workspace / "explicit.py"
    explicit.write_text(
        'git("rebase", "--onto", new, old, branch)\n'
        'run_process(["git", "rebase", base, "--update-refs"])\n'
        'git("rebase", "--abort")\n'
    )
    fixture = workspace / "fixture.py"
    fixture.write_text(
        'example = ["git", "rebase", "main"]\n'
        'record_example(["git", "rebase", "main"])\n'
    )

    assert checker.check_implicit_rebase([], [explicit, fixture]) == []


def test_check_metadata_source_handles_nested_indentation(workspace):
    existing = workspace / "metadata-source-target.md"
    existing.write_text("target\n")
    document = workspace / "skill.md"
    source_path = existing.relative_to(ROOT)
    document.write_text(
        "---\n"
        "  metadata:\n"
        "      source:\n"
        f"          - {source_path}\n"
        "          - tmp/missing-source-target.md\n"
        "---\n"
    )
    findings = checker.check_metadata_source([document])

    assert len(findings) == 1
    assert "tmp/missing-source-target.md" in findings[0][3]


def test_check_metadata_source_rejects_path_outside_repo(workspace):
    document = workspace / "skill.md"
    document.write_text("---\nmetadata:\n  source: ../../outside.md\n---\n")

    findings = checker.check_metadata_source([document])

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR
    assert "outside the repository" in findings[0][3]


def test_check_metadata_source_ignores_template_placeholders(workspace):
    document = workspace / "skill-template.md"
    document.write_text(
        "---\nmetadata:\n  source: <relevant source command or tool>\n---\n"
    )

    assert checker.check_metadata_source([document]) == []


def test_cli_reports_unreadable_file_as_error(workspace, monkeypatch, capsys):
    document = workspace / "instructions.md"
    document.write_text("content\n")
    real_open = builtins.open

    def fail_target(path, *args, **kwargs):
        if Path(path) == document:
            raise PermissionError("denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_target)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--dir", str(document)])

    with pytest.raises(SystemExit, match="1"):
        checker.main()

    output = capsys.readouterr()
    assert "[ERR]" in output.out
    assert "denied" in output.out


def test_cli_warnings_do_not_fail(workspace):
    document = workspace / "instructions.md"
    document.write_text("Run `python script.py`.\n")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(document)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "[WARN]" in result.stdout
    assert "No issues found" not in result.stdout


def test_check_command_dependencies_reports_missing_declared_skill(workspace):
    commands = workspace / "commands"
    skills = workspace / "skills"
    commands.mkdir()
    skills.mkdir()
    command = commands / "deploy.md"
    command.write_text(
        "Read root `AGENTS.md` and load `missing-skill`.\n\n"
        "## Required Context\n\n- Skills `also-missing`; template `example`.\n"
    )

    findings = checker.check_command_dependencies(commands, skills)

    assert len(findings) == 2
    assert all(finding[0] == checker.SEV_ERR for finding in findings)
    assert {finding[2] for finding in findings} == {1, 5}
    assert all("skill" in finding[3] for finding in findings)


def test_check_command_dependencies_ignores_templates_and_general_prose(workspace):
    commands = workspace / "commands"
    skills = workspace / "skills"
    commands.mkdir()
    skills.mkdir()
    command = commands / "deploy.md"
    command.write_text(
        "Use `example-skill` when useful.\n"
        "Template: load `<skill-name>`.\n"
        "## Required Context\n\n- Template `<skill>`; file `notes`.\n"
    )

    assert checker.check_command_dependencies(commands, skills) == []


def test_check_command_dependencies_reports_missing_common_module(workspace):
    commands = workspace / "commands"
    skills = workspace / "skills"
    commands.mkdir()
    skills.mkdir()
    command = commands / "review.md"
    command.write_text("Read `_common-missing.md`.\n")

    findings = checker.check_command_dependencies(commands, skills)

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR
    assert findings[0][2] == 1
    assert "_common-missing.md" in findings[0][3]


def test_check_command_dependencies_requires_two_common_module_consumers(workspace):
    commands = workspace / "commands"
    skills = workspace / "skills"
    commands.mkdir()
    skills.mkdir()
    common = commands / "_common-review.md"
    common.write_text("Shared review instructions.\n")
    (commands / "review.md").write_text("Read `_common-review.md`.\n")

    findings = checker.check_command_dependencies(commands, skills)

    assert len(findings) == 1
    assert findings[0][0] == checker.SEV_ERR
    assert findings[0][1] == str(common)
    assert findings[0][2] is None
    assert "2 command consumers" in findings[0][3]

    (commands / "review-again.md").write_text("Read `_common-review.md`.\n")
    assert checker.check_command_dependencies(commands, skills) == []


def test_default_cli_runs_command_dependency_checks(workspace, monkeypatch, capsys):
    agents = workspace / ".agents"
    commands = agents / "commands"
    skills = agents / "skills"
    commands.mkdir(parents=True)
    skills.mkdir()
    (commands / "deploy.md").write_text("Load `missing-skill`.\n")
    monkeypatch.setattr(checker.repo_guard, "repo_root", lambda: workspace)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit, match="1"):
        checker.main()

    output = capsys.readouterr()
    assert "missing-skill" in output.out


def test_check_command_map_requires_each_public_command_exactly_once(workspace):
    commands = workspace / "commands"
    commands.mkdir()
    (commands / "README.md").write_text(
        "| Command | Workflow |\n|---|---|\n"
        "| `/plan` | Plan work |\n| `/plan` | Duplicate example |\n"
    )
    (commands / "plan.md").write_text("Plan.\n")
    (commands / "implement.md").write_text("Implement.\n")
    (commands / "_common-review.md").write_text("Internal.\n")

    findings = checker.check_command_map(commands)

    assert len(findings) == 2
    assert any("'/plan' appears 2 times" in finding[3] for finding in findings)
    assert any("'/implement' is missing" in finding[3] for finding in findings)
    assert all("_common-review" not in finding[3] for finding in findings)


def test_check_command_map_reports_entries_without_public_command_files(workspace):
    commands = workspace / "commands"
    commands.mkdir()
    readme = commands / "README.md"
    readme.write_text(
        "Example: `/future-command` is not a mapped row.\n\n"
        "| Command | Workflow |\n|---|---|\n"
        "| `/plan` | Plan work |\n| `/_common-review` | Internal |\n"
        "| `/missing` | Missing |\n"
    )
    (commands / "plan.md").write_text("Plan.\n")
    (commands / "_common-review.md").write_text("Internal.\n")

    findings = checker.check_command_map(commands)

    assert len(findings) == 2
    assert any("internal command" in finding[3] for finding in findings)
    assert any("'/missing' has no command file" in finding[3] for finding in findings)
    assert all("future-command" not in finding[3] for finding in findings)


def test_check_skills_validates_file_name_and_description(workspace):
    skills = workspace / "skills"
    skills.mkdir()
    valid = skills / "valid"
    valid.mkdir()
    (valid / "SKILL.md").write_text(
        "---\nname: valid\ndescription: Useful skill\n---\n"
    )
    missing = skills / "missing"
    missing.mkdir()
    mismatch = skills / "mismatch"
    mismatch.mkdir()
    (mismatch / "SKILL.md").write_text(
        "---\nname: other\ndescription: Useful skill\n---\n"
    )
    empty = skills / "empty"
    empty.mkdir()
    (empty / "SKILL.md").write_text(
        "---\nname: empty\ndescription:   \n---\n"
        "Example: name: example and description: placeholder\n"
    )

    findings = checker.check_skills(skills)

    assert len(findings) == 3
    assert any("missing SKILL.md" in finding[3] for finding in findings)
    assert any("does not match directory" in finding[3] for finding in findings)
    assert any("nonempty frontmatter description" in finding[3] for finding in findings)


def test_default_cli_runs_command_map_and_skill_checks(workspace, monkeypatch, capsys):
    agents = workspace / ".agents"
    commands = agents / "commands"
    skills = agents / "skills"
    commands.mkdir(parents=True)
    skills.mkdir()
    (commands / "README.md").write_text(
        "| Command | Workflow |\n|---|---|\n| `/missing` | Missing |\n"
    )
    skill = skills / "broken"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: wrong\ndescription: Broken skill\n---\n"
    )
    monkeypatch.setattr(checker.repo_guard, "repo_root", lambda: workspace)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit, match="1"):
        checker.main()

    output = capsys.readouterr()
    assert "'/missing' has no command file" in output.out
    assert "does not match directory" in output.out
