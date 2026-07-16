import importlib.util
import shutil
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "review_log", Path(__file__).parent.parent / "review-log.py"
)
review_log = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(review_log)
ORIGINAL_GET_BRANCH = review_log.get_branch


def finding(
    finding_id="CORRECTNESS-PARSER-001",
    status="ADDRESSED",
    severity="HIGH",
    category="CORRECTNESS",
):
    status_line = f"**Status**: {status}\n" if status is not None else ""
    return (
        f"### [{finding_id}] - [{severity}] - Regression\n\n"
        f"{status_line}\n"
        f"**Severity**: {severity}\n\n"
        f"**Category**: {category}\n\n"
        "**Location**: src/parser.py:10\n\n"
        "**Description**:\nThe parser accepts malformed input.\n\n"
        "**Why It Matters**:\nInvalid reports can be archived.\n\n"
        "**Suggested Fix**:\nFix it.\n\n"
        "**How to Validate**:\n```bash\nuv run pytest tests/test_parser.py\n```\n\n"
        "**Expected Addressed Result**:\nThe command exits 0.\n\n"
        "---\n"
    )


def report(*findings, head="b" * 40, branch="test"):
    body = "\n".join(findings) if findings else "No findings.\n"
    return f"# Review Report: Test\n\n**Branch**: {branch}\n**Scope**: parser\n**Commit Range**: {'a' * 40}...{head}\n\n## Findings\n\n{body}"


@pytest.fixture
def workspace(monkeypatch):
    path = ROOT / "tmp" / f"test-review-log-{uuid.uuid4().hex}"
    path.mkdir()
    monkeypatch.chdir(path)
    monkeypatch.setattr(review_log, "get_branch", lambda: "test")
    yield path
    shutil.rmtree(path)


def write_review(workspace, content):
    path = workspace / "review.md"
    path.write_text(content)
    return path


def test_parse_review_findings_accepts_canonical_bracketed_multi_segment_id(workspace):
    review = write_review(workspace, report(finding()))

    findings = review_log.parse_review_findings(str(review))

    assert findings[0]["id"] == "CORRECTNESS-PARSER-001"


def test_review_log_uses_shared_schema_parser(monkeypatch, workspace):
    review = write_review(workspace, report(finding()))
    called = []
    original = review_log.review_common.parse_findings
    monkeypatch.setattr(
        review_log.review_common,
        "parse_findings",
        lambda content: called.append(content) or original(content),
    )

    review_log.parse_review_findings(str(review))

    assert called == [review.read_text()]


@pytest.mark.parametrize("status", ["OPEN", "ADDRESSED", "INVALID", "DEFERRED"])
def test_parse_review_findings_accepts_every_status(workspace, status):
    review = write_review(workspace, report(finding(status=status)))

    findings = review_log.parse_review_findings(str(review))

    assert findings[0]["status"] == status.lower()


def test_parse_review_findings_accepts_clean_report(workspace):
    review = write_review(workspace, report())

    assert review_log.parse_review_findings(str(review)) == []


def test_log_create_rejects_hidden_second_findings_section_without_writing_log(
    workspace,
):
    review = write_review(
        workspace,
        report() + "\n## Findings\n\n" + finding(status="OPEN"),
    )

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert not review_log.get_log_path("test").exists()


@pytest.mark.parametrize(
    "invalid_finding",
    [
        finding().replace("**Category**: CORRECTNESS\n\n", ""),
        finding().replace("**Location**: src/parser.py:10\n\n", ""),
        finding().replace(
            "**Description**:\nThe parser accepts malformed input.\n\n", ""
        ),
        finding().replace(
            "**Why It Matters**:\nInvalid reports can be archived.\n\n", ""
        ),
        finding().replace("**Suggested Fix**:\nFix it.\n\n", ""),
        finding().replace(
            "**How to Validate**:\n```bash\nuv run pytest tests/test_parser.py\n```\n\n",
            "",
        ),
        finding().replace(
            "**Expected Addressed Result**:\nThe command exits 0.\n\n", ""
        ),
        finding(finding_id="CORRECTNESS-001"),
        finding(finding_id="correctness-parser-001"),
        finding(severity="MAJOR"),
        finding(category="SECURITY"),
        finding().replace(
            "**Description**:\n",
            "**Legacy Field**: unsupported\n\n**Description**:\n",
        ),
    ],
)
def test_parse_review_findings_rejects_malformed_finding(workspace, invalid_finding):
    review = write_review(workspace, report(invalid_finding))

    with pytest.raises(ValueError, match="Malformed review finding"):
        review_log.parse_review_findings(str(review))


def test_parse_review_findings_rejects_noncanonical_clean_report(workspace):
    review = write_review(workspace, report("Everything looks good."))

    with pytest.raises(ValueError, match="No findings"):
        review_log.parse_review_findings(str(review))


def test_log_create_rejects_open_only_without_writing_log(workspace):
    review = write_review(workspace, report(finding(status="OPEN")))

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert not review_log.get_log_path("test").exists()


def test_log_create_rejects_mixed_open_and_closed_without_writing_log(workspace):
    review = write_review(
        workspace,
        report(
            finding("CORRECTNESS-PARSER-001", "OPEN"),
            finding("CORRECTNESS-PARSER-002", "ADDRESSED"),
        ),
    )

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert not review_log.get_log_path("test").exists()


@pytest.mark.parametrize("status", ["UNKNOWN", None])
def test_log_create_rejects_malformed_or_missing_status_without_writing_log(
    workspace, status
):
    review = write_review(workspace, report(finding(status=status)))

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert not review_log.get_log_path("test").exists()


def test_log_create_failure_does_not_modify_existing_log(workspace):
    review = write_review(workspace, report(finding(status="OPEN")))
    log_path = review_log.get_log_path("test")
    log_path.parent.mkdir(parents=True)
    log_path.write_text("existing log\n")

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert log_path.read_text() == "existing log\n"


def test_log_create_ignores_current_git_failure_for_explicit_report(
    workspace, monkeypatch
):
    review = write_review(workspace, report())
    log_path = review_log.get_log_path("test")
    log_path.parent.mkdir(parents=True)
    log_path.write_text("existing log\n")
    monkeypatch.setattr(review_log, "get_branch", ORIGINAL_GET_BRANCH)

    def fail_git(_command):
        raise review_log.ExternalCommandError(["git"], "git failed")

    monkeypatch.setattr(review_log, "run_process", fail_git)

    result = review_log.cmd_log_create(str(review))

    assert result == 0
    assert "**Cycle Key**: test:" in log_path.read_text()


def test_log_create_ignores_detached_head_for_explicit_report(workspace, monkeypatch):
    review = write_review(workspace, report())
    monkeypatch.setattr(review_log, "get_branch", ORIGINAL_GET_BRANCH)
    monkeypatch.setattr(review_log, "run_process", lambda _command: "")

    result = review_log.cmd_log_create(str(review))

    assert result == 0
    assert review_log.get_log_path("test").exists()


def test_log_create_rejects_malformed_finding_without_writing_log(workspace):
    malformed = finding().replace("**Location**: src/parser.py:10\n\n", "")
    review = write_review(workspace, report(malformed))

    result = review_log.cmd_log_create(str(review))

    assert result == 1
    assert not review_log.get_log_path("test").exists()


def test_log_create_preserves_canonical_finding_fields(workspace):
    review = write_review(workspace, report(finding()))

    result = review_log.cmd_log_create(str(review))

    content = review_log.get_log_path("test").read_text()
    assert result == 0
    assert "### [CORRECTNESS-PARSER-001] - [HIGH] - Regression" in content
    for field in (
        "Status",
        "Severity",
        "Category",
        "Location",
        "Description",
        "Why It Matters",
        "Suggested Fix",
        "How to Validate",
        "Expected Addressed Result",
    ):
        assert f"**{field}**:" in content


def test_log_create_is_idempotent_for_same_branch_and_head(workspace):
    review = write_review(workspace, report())

    assert review_log.cmd_log_create(str(review)) == 0
    assert review_log.cmd_log_create(str(review)) == 0

    content = review_log.get_log_path("test").read_text()
    assert content.count("[REVIEW_1_START]") == 1
    assert f"**Cycle Key**: test:{'b' * 40}" in content


def test_log_create_uses_explicit_report_branch_not_current_branch(workspace):
    review = write_review(workspace, report(branch="feature/explicit"))

    assert review_log.cmd_log_create(str(review)) == 0
    assert review_log.get_log_path("feature/explicit").exists()
    assert not review_log.get_log_path("test").exists()
