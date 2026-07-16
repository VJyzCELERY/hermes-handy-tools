import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "review_common", SCRIPTS / "review_common.py"
)
review_common = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(review_common)


def finding(status="OPEN"):
    return f"""### [CORRECTNESS-PARSER-001] - [HIGH] - Reject bad input

**Status**: {status}

**Severity**: HIGH

**Category**: CORRECTNESS

**Location**: src/parser.py:10

**Description**:
Bad input is accepted.

**Why It Matters**:
Results are incorrect.

**Suggested Fix**:
Reject it.

**How to Validate**:
```bash
uv run pytest
```

**Expected Addressed Result**:
The command exits 0.
"""


def report(body, head="b" * 40, remote=""):
    return f"""# Review Report: Test

**Branch**: feature
**Commit Range**: {"a" * 40}...{head}

## Findings

{body}
{remote}"""


def test_classify_all_local_states(tmp_path):
    path = tmp_path / "REVIEW_test.md"
    assert review_common.classify_report(path, "b" * 40)["state"] == "ABSENT"

    path.write_text(report(finding()))
    assert review_common.classify_report(path, "b" * 40)["state"] == "ACTIVE_OPEN"

    path.write_text(report(finding("ADDRESSED")))
    assert review_common.classify_report(path, "b" * 40)["state"] == "COMPLETE"

    path.write_text(report("No findings."))
    assert review_common.classify_report(path, "b" * 40)["state"] == "CLEAN"
    assert review_common.classify_report(path, "c" * 40)["state"] == "STALE"

    path.write_text(report("not canonical"))
    assert review_common.classify_report(path, "b" * 40)["state"] == "MALFORMED"

    archived = (
        review_common.repo_guard.repo_root()
        / "reviews"
        / "archives"
        / f"test-{tmp_path.name}.md"
    )
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text(report("No findings."))
    try:
        assert review_common.classify_report(archived, "b" * 40)["state"] == "ARCHIVED"
    finally:
        archived.unlink()


def test_classify_only_canonical_archives_subtree_as_archived(tmp_path, monkeypatch):
    monkeypatch.setattr(review_common.repo_guard, "repo_root", lambda: tmp_path)
    canonical = tmp_path / "reviews" / "archives" / "REVIEW_test.md"
    canonical.parent.mkdir(parents=True)
    canonical.write_text(report("No findings."))
    lookalike = tmp_path / "archive" / "REVIEW_test.md"
    lookalike.parent.mkdir()
    lookalike.write_text(report("No findings."))

    assert review_common.classify_report(canonical)["state"] == "ARCHIVED"
    assert review_common.classify_report(lookalike)["state"] == "CLEAN"


def test_report_paths_reject_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "report.md").write_text(report("No findings."))
    (root / "reviews").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(review_common.repo_guard, "repo_root", lambda: root)

    with pytest.raises(ValueError, match="escapes"):
        review_common.read_report(root / "reviews" / "report.md")


def test_parse_remote_feedback_and_preserve_old_reports_as_unlinked(tmp_path):
    path = tmp_path / "REVIEW_test.md"
    path.write_text(report("No findings."))
    assert review_common.read_report(path)["remote_feedback"] == "UNLINKED"

    remote = """
## Remote Feedback

```json
{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[]}
```
"""
    path.write_text(report("No findings.", remote=remote))
    parsed = review_common.read_report(path)
    assert parsed["remote_feedback"]["pull_request"].endswith("/pull/7")

    path.write_text(report("No findings.", remote="\n## Remote Feedback\n\nUNLINKED\n"))
    assert review_common.read_report(path)["remote_feedback"] == "UNLINKED"


def test_parse_findings_returns_shared_log_schema():
    parsed = review_common.parse_findings(report(finding("ADDRESSED")))

    assert parsed[0]["severity"] == "high"
    assert parsed[0]["category"] == "correctness"
    assert parsed[0]["location"] == "src/parser.py:10"
    assert parsed[0]["problem"] == "Bad input is accepted."
    assert parsed[0]["validation"] == "uv run pytest"


@pytest.mark.parametrize("payload", ["[]", "{}", "{bad json"])
def test_remote_feedback_rejects_malformed_json_schema(tmp_path, payload):
    path = tmp_path / "REVIEW_test.md"
    remote = f"\n## Remote Feedback\n\n```json\n{payload}\n```\n"
    path.write_text(report("No findings.", remote=remote))
    with pytest.raises(ValueError, match="Remote Feedback"):
        review_common.read_report(path)


@pytest.mark.parametrize(
    "payload",
    [
        '{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[],"extra":true}',
        '{"repository":7,"pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[]}',
        '{"repository":"https://example.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[]}',
        '{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"short","items":[]}',
        '{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[{"url":"https://github.com/acme/widgets/pull/7#discussion_r9","reply":7}]}',
        '{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[{"url":"https://github.com/acme/widgets/pull/7#discussion_r9","reply":"fixed","extra":true}]}',
        '{"repository":"https://github.com/acme/widgets","pull_request":"https://github.com/acme/widgets/pull/7","head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","items":[{"url":"https://github.com/acme/widgets/pull/7#discussion_r9","reply":"fixed"},{"url":"https://github.com/acme/widgets/pull/7#discussion_r9","reply":"fixed again"}]}',
    ],
)
def test_remote_feedback_rejects_noncanonical_linked_schema(tmp_path, payload):
    path = tmp_path / "REVIEW_test.md"
    path.write_text(
        report(
            "No findings.", remote=f"\n## Remote Feedback\n\n```json\n{payload}\n```\n"
        )
    )

    with pytest.raises(ValueError, match="Remote Feedback"):
        review_common.read_report(path)
