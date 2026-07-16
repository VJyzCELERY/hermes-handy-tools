"""Review log management script.

Creates, validates, and browses review log entries stored in
./reviews/log/REVIEW_{normalized_branch}.md format.

Usage:
    uv run python .agents/scripts/review-log.py --log-create <review-path>
    uv run python .agents/scripts/review-log.py --validate <log-path>
    uv run python .agents/scripts/review-log.py --next-id <log-path>
    uv run python .agents/scripts/review-log.py --browse <log-path> [--page N]
<EOF_DESC>
"""

import argparse
import datetime
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard
import review_common
from cli_common import EXIT_EXTERNAL, ExternalCommandError, run_process


FINDING_ID = r"[A-Z][A-Z0-9]*-[A-Z][A-Z0-9]*-\d{3}"
STATUSES = {"OPEN", "ADDRESSED", "INVALID", "DEFERRED"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def get_branch() -> str:
    command = ["git", "branch", "--show-current"]
    branch = run_process(command)
    if not branch:
        raise ExternalCommandError(command, "Detached HEAD; cannot determine branch")
    return branch.replace("/", "_")


def get_log_path(branch: str | None = None) -> Path:
    if not branch:
        branch = get_branch()
    branch = branch.replace("/", "_")
    return repo_guard.assert_inside_repo(Path("./reviews/log") / f"REVIEW_{branch}.md")


def get_next_entry_id(log_path: Path) -> int:
    log_path = repo_guard.assert_inside_repo(log_path)
    if not log_path.exists():
        return 1
    content = log_path.read_text()
    pattern = r"\[REVIEW_(\d+)_START\]"
    matches = re.findall(pattern, content)
    if not matches:
        return 1
    return max(int(m) for m in matches) + 1


def parse_review_findings(review_path: str) -> list[dict]:
    """Parse a canonical findings section, rejecting malformed reports."""
    content = repo_guard.assert_inside_repo(review_path).read_text()
    return review_common.parse_findings(content)


def format_finding(f: dict) -> str:
    return (
        f"### [{f['id']}] - [{f['severity'].upper()}] - {f['title']}\n\n"
        f"**Status**: {f['status'].upper()}\n\n"
        f"**Severity**: {f['severity'].upper()}\n\n"
        f"**Category**: {f['category'].upper()}\n\n"
        f"**Location**: {f['location']}\n\n"
        f"**Description**:\n{f['problem']}\n\n"
        f"**Why It Matters**:\n{f['impact']}\n\n"
        f"**Suggested Fix**:\n{f['resolution']}\n\n"
        f"**How to Validate**:\n```bash\n{f['validation']}\n```\n\n"
        f"**Expected Addressed Result**:\n{f['expected_result']}\n"
    )


def write_atomic(path: Path, content: str) -> None:
    """Replace a repository file atomically using its own directory."""
    path = repo_guard.assert_inside_repo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8"
        ) as temp_file:
            temp_file.write(content)
            temp_path = repo_guard.assert_inside_repo(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def cmd_log_create(review_path: str) -> int:
    try:
        review_file = repo_guard.assert_inside_repo(review_path)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    if not review_file.exists():
        print(f"[ERROR] Review file not found: {review_path}", file=sys.stderr)
        return 1

    try:
        report = review_common.read_report(review_file)
        findings = report["findings"]
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    invalid_findings = [
        finding
        for finding in findings
        if finding["status"] not in ("addressed", "invalid", "deferred")
    ]
    if invalid_findings:
        invalid_ids = ", ".join(finding["id"] for finding in invalid_findings)
        print(
            f"[ERROR] Review has OPEN, malformed, or missing statuses: {invalid_ids}",
            file=sys.stderr,
        )
        return 1

    branch = report["branch"].replace("/", "_")
    cycle_key = f"{branch}:{report['head']}"
    log_path = get_log_path(branch)
    if log_path.exists() and f"**Cycle Key**: {cycle_key}" in log_path.read_text():
        print(f"[OK] Review already logged: {log_path} ({cycle_key})")
        return 0

    if not findings:
        # Approved review with 0 findings — log an approval entry
        entry_id = get_next_entry_id(log_path)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

        review_content = review_file.read_text()
        scope_match = re.search(r"\*\*Scope\*\*:\s*(.+)", review_content)
        scope = scope_match.group(1).strip() if scope_match else ""

        entry = (
            f"---\n\n"
            f"[REVIEW_{entry_id}_START]\n"
            f"---\n\n"
            f"**Review Date**: {date_str}\n"
            f"**Scope**: {scope}\n"
            f"**Cycle**: {entry_id}\n"
            f"**Cycle Key**: {cycle_key}\n"
            f"**Total Findings**: 0 | **Resolved**: 0 | **Deferred**: 0 | **Invalid**: 0\n"
            f"\n"
            f"### Approval — 0 findings, clean review\n"
            f"- **Status**: approved\n"
            f"- **Assessment**: No issues found. Review passed clean.\n"
            f"\n"
            f"---\n\n"
            f"[REVIEW_{entry_id}_END]\n"
        )

        if log_path.exists():
            existing = log_path.read_text().rstrip()
            write_atomic(log_path, existing + "\n" + entry)
        else:
            header = f"# Review Log: {branch}\n\n"
            write_atomic(log_path, header + entry)

        print(f"[OK] Approved review logged: {log_path} (entry REVIEW_{entry_id})")
        return 0

    entry_id = get_next_entry_id(log_path)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Get scope from review file header
    scope = ""
    review_content = review_file.read_text()
    scope_match = re.search(r"\*\*Scope\*\*:\s*(.+)", review_content)
    if scope_match:
        scope = scope_match.group(1).strip()

    # Count statuses
    total = len(findings)
    resolved = sum(1 for f in findings if f["status"] == "addressed")
    deferred = sum(1 for f in findings if f["status"] == "deferred")
    invalid = sum(1 for f in findings if f["status"] == "invalid")

    # Build findings section
    findings_text = "\n".join(format_finding(f) for f in findings)

    entry = (
        f"---\n\n"
        f"[REVIEW_{entry_id}_START]\n"
        f"---\n\n"
        f"**Review Date**: {date_str}\n"
        f"**Scope**: {scope}\n"
        f"**Cycle**: {entry_id}\n"
        f"**Cycle Key**: {cycle_key}\n"
        f"**Total Findings**: {total} | **Resolved**: {resolved} | **Deferred**: {deferred} | **Invalid**: {invalid}\n"
        f"\n"
        f"---\n\n"
        f"{findings_text}"
        f"---\n\n"
        f"[REVIEW_{entry_id}_END]\n"
    )

    # Create or append
    if log_path.exists():
        existing = log_path.read_text().rstrip()
        # Insert before trailing newline or append
        if existing.endswith("---"):
            write_atomic(log_path, existing + "\n" + entry)
        else:
            write_atomic(log_path, existing + "\n" + entry)
    else:
        header = f"# Review Log: {branch}\n\n"
        write_atomic(log_path, header + entry)

    print(f"[OK] Review logged: {log_path} (entry REVIEW_{entry_id})")
    return 0


def cmd_validate(log_path: str) -> int:
    try:
        p = repo_guard.assert_inside_repo(log_path)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    if not p.exists():
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        return 1

    content = p.read_text()
    errors = []

    # Check header
    if not content.startswith("# Review Log:"):
        errors.append("Missing '# Review Log:' header")

    # Check entry delimiters
    starts = re.findall(r"\[REVIEW_(\d+)_START\]", content)
    ends = re.findall(r"\[REVIEW_(\d+)_END\]", content)

    if not starts:
        errors.append("No review entries found")

    if len(starts) != len(ends):
        errors.append(f"Mismatched delimiters: {len(starts)} START, {len(ends)} END")

    # Check sequential ID ordering
    for i in range(len(starts) - 1):
        if int(starts[i]) >= int(starts[i + 1]):
            errors.append(
                f"Entry IDs not sequential: REVIEW_{starts[i]} followed by REVIEW_{starts[i + 1]}"
            )

    # Validate each entry
    for sid, eid in zip(starts, ends):
        if sid != eid:
            errors.append(f"Entry ID mismatch: START={sid}, END={eid}")

    if errors:
        print(f"[ERROR] {len(errors)} validation issue(s):")
        for e in errors:
            print(f"       - {e}")
        return 1

    print(f"[OK] Log valid: {len(starts)} entry(ies), format correct.")
    return 0


def cmd_next_id(log_path: str) -> int:
    try:
        path = repo_guard.assert_inside_repo(log_path) if log_path else get_log_path()
        next_id = get_next_entry_id(path)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    except ExternalCommandError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(next_id)
    return 0


def cmd_browse(log_path: str, page: int = 1, per_page: int = 1) -> int:
    try:
        p = repo_guard.assert_inside_repo(log_path)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    if not p.exists():
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        return 1

    content = p.read_text()
    entries = re.findall(
        r"\[REVIEW_(\d+)_START\]\n---\n(.*?)\n---\n\[REVIEW_\1_END\]",
        content,
        re.DOTALL,
    )

    if not entries:
        print("[INFO] No entries found.")
        return 0

    total = len(entries)
    start = (page - 1) * per_page
    end = start + per_page

    if start >= total:
        print(f"[INFO] Page {page} exceeds total {total} entries.")
        return 0

    for i in range(start, min(end, total)):
        eid, body = entries[i]
        print(f"{'=' * 60}")
        print(f"  Entry REVIEW_{eid} ({i + 1}/{total})")
        print(f"{'=' * 60}")
        print(f"\n{body.strip()}\n")

    if end < total:
        print(f"--- Page {page} — use --page {page + 1} for next ---")
    else:
        print("--- End of log ---")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Review log management")
    parser.add_argument(
        "--log-create", type=str, default=None, help="Path to review report to log"
    )
    parser.add_argument(
        "--validate", type=str, default=None, help="Validate a review log file"
    )
    parser.add_argument(
        "--next-id",
        type=str,
        default=None,
        const="",
        nargs="?",
        help="Get next entry ID for a log (omit path for default)",
    )
    parser.add_argument(
        "--browse", type=str, default=None, help="Browse a review log file"
    )
    parser.add_argument(
        "--page", type=int, default=1, help="Page number for browse (default: 1)"
    )
    args = parser.parse_args()

    if args.log_create:
        return cmd_log_create(args.log_create)

    if args.validate:
        return cmd_validate(args.validate)

    if args.next_id is not None:
        path = args.next_id if args.next_id else ""
        return cmd_next_id(path)

    if args.browse:
        return cmd_browse(args.browse, args.page)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
