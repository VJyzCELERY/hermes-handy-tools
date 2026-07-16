import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "review_log_schema", ROOT / ".agents" / "scripts" / "review-log.py"
)
review_log = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(review_log)


def test_review_template_example_matches_parser():
    template = ROOT / ".agents" / "templates" / "REVIEW-template.md"

    findings = review_log.parse_review_findings(str(template))

    assert len(findings) == 1
    assert findings[0]["id"] == "CORRECTNESS-PARSER-001"
    assert "## Remote Feedback\n\nUNLINKED" in template.read_text()


def test_posting_templates_use_canonical_finding_fields():
    for name in (
        "review-body-snippet.md",
        "inline-comment-body-snippet.md",
        "inline-comment-format.json",
    ):
        content = (ROOT / ".agents" / "templates" / name).read_text()
        assert "<CATEGORY-SUBJECT-NNN>" in content
        assert "<category>" in content
        assert "<location>" in content
        assert "<description>" in content
        assert "<expected-addressed-result>" in content


def test_review_command_inventory_matches_baseline_model():
    commands = ROOT / ".agents" / "commands"
    assert (commands / "review.md").exists()
    for removed in (
        "review-report.md",
        "review-loop.md",
        "review-clarify.md",
        "review-verify.md",
    ):
        assert not (commands / removed).exists()

    validate = (commands / "review-validate.md").read_text()
    assert "review-clarify.md" not in validate
    assert "review-verify.md" not in validate
    assert "review.md" not in validate


def test_review_commands_use_archives_path_and_sync_gate():
    commands = ROOT / ".agents" / "commands"
    assert "reviews/archives" in (commands / "review.md").read_text()
    assert "--sync-remote" in (commands / "review.md").read_text()
    assert "reviews/archives" in (commands / "review-archive.md").read_text()
