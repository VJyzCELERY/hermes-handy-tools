"""Review log management script.

Creates, validates, and browses review log entries stored in
./reviews/log/REVIEW_{branch}.md format.

Usage:
    uv run python .agents/scripts/review-log.py --log-create <review-path>
    uv run python .agents/scripts/review-log.py --validate <log-path>
    uv run python .agents/scripts/review-log.py --next-id <log-path>
    uv run python .agents/scripts/review-log.py --browse <log-path> [--page N]
<EOF_DESC>
"""

import subprocess, sys, re, argparse, datetime
from pathlib import Path


def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""


def get_branch() -> str:
    branch = run(["git", "branch", "--show-current"])
    return branch.replace("/", "-") if branch else "unknown"


def get_log_path(branch: str | None = None) -> Path:
    if not branch:
        branch = get_branch()
    return Path("./reviews/log") / f"REVIEW_{branch}.md"


def get_next_entry_id(log_path: Path) -> int:
    if not log_path.exists():
        return 1
    content = log_path.read_text()
    pattern = r'\[REVIEW_(\d+)_START\]'
    matches = re.findall(pattern, content)
    if not matches:
        return 1
    return max(int(m) for m in matches) + 1


def parse_review_findings(review_path: str) -> list[dict]:
    """Parse findings from a review report.

    Returns findings with status addressed, invalid, or deferred (skips OPEN).
    """
    content = Path(review_path).read_text()
    findings = []

    finding_blocks = re.split(r'^###\s+', content, flags=re.MULTILINE)
    for block in finding_blocks[1:]:  # Skip text before first ###
        finding = {"id": "", "title": "", "severity": "", "category": "",
                    "status": "", "problem": "", "validation": "",
                    "resolution": "", "reasoning": ""}

        # Flexible ID matching — supports ISSUE-001, F-001, BUG-42, or any word-number pattern
        id_match = re.match(r'([A-Za-z]+-\d+)', block)
        if id_match:
            finding["id"] = id_match.group(1)

        # Flexible title extraction: use the entire first line, stripping ID prefix and severity
        first_line = block.split('\n')[0].strip()
        # Try to extract a meaningful title by stripping {ID} or {ID - SEVERITY - } prefix
        title = first_line
        # Strip the ID prefix (e.g. "ISSUE-001", "F-001")
        title = re.sub(r'^[A-Za-z]+-\d+\s*[-:]\s*', '', title)
        # Strip severity prefix (e.g. "CRITICAL - ", "MEDIUM - ")
        title = re.sub(r'^[A-Z]+\s*-\s*', '', title)
        if title:
            finding["title"] = title
        elif id_match:
            finding["title"] = id_match.group(1)

        status_match = re.search(r'\*\*Status\*\*:\s*(\w+)', block)
        if status_match:
            status = status_match.group(1).upper()
            if status in ("ADDRESSED", "INVALID", "DEFERRED"):
                finding["status"] = status.lower()
            else:
                continue  # Skip OPEN findings

        sev_match = re.search(r'\*\*Severity\*\*:\s*(\w+)', block)
        if sev_match:
            finding["severity"] = sev_match.group(1).lower()

        cat_match = re.search(r'\*\*Category\*\*:\s*(\w+)', block)
        if cat_match:
            finding["category"] = cat_match.group(1).lower()

        # Use --- or end of block as section boundary (not \n\n which breaks on code blocks)
        section_end = r'(?:\n---|\Z)'

        # Problem is the paragraph after Status/Severity, before Location or Why It Matters
        problem_match = re.search(r'\*\*Severity\*\*:\s*\w+\s*\n\n(.*?)(?=\n\*\*(?:Location|Why It Matters|Suggested Fix))', block, re.DOTALL)
        if problem_match:
            finding["problem"] = problem_match.group(1).strip()
        else:
            # Fallback: between Location and Suggested Fix
            problem_match = re.search(r'\*\*Location\*\*:\s*(.*?)' + section_end, block, re.DOTALL)
            if problem_match:
                finding["problem"] = problem_match.group(1).strip()

        # Resolution = Suggested Fix content (before How to Validate or ---)
        res_match = re.search(r'\*\*Suggested Fix\*\*:\s*(.*?)(?=\n\*\*How to Validate|\n---|\Z)', block, re.DOTALL)
        if res_match:
            finding["resolution"] = res_match.group(1).strip()

        # Validation method
        val_match = re.search(r'\*\*How to Validate\*\*:\s*(.*?)' + section_end, block, re.DOTALL)
        if val_match:
            finding["validation"] = val_match.group(1).strip()

        findings.append(finding)

    return findings


def format_finding(f: dict) -> str:
    lines = [
        f"### {f['id']}: {f['title']}",
        f"- **Severity**: {f['severity']} | **Category**: {f['category']}",
        f"- **Status**: {f['status']}",
    ]
    if f["problem"]:
        lines.append(f"- **Problem**: {f['problem']}")
    if f["validation"]:
        lines.append(f"- **Validation**: {f['validation']}")
    if f["resolution"]:
        lines.append(f"- **Resolution**: {f['resolution']}")
    if f["reasoning"]:
        lines.append(f"- **Reasoning**: {f['reasoning']}")
    return "\n".join(lines) + "\n"


def cmd_log_create(review_path: str) -> int:
    if not Path(review_path).exists():
        print(f"[ERROR] Review file not found: {review_path}", file=sys.stderr)
        return 1

    findings = parse_review_findings(review_path)
    if not findings:
        # Approved review with 0 findings — log an approval entry
        branch = get_branch()
        log_dir = Path("./reviews/log")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = get_log_path(branch)
        entry_id = get_next_entry_id(log_path)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

        review_content = Path(review_path).read_text()
        scope_match = re.search(r'\*\*Scope\*\*:\s*(.+)', review_content)
        scope = scope_match.group(1).strip() if scope_match else ""

        entry = (
            f"---\n\n"
            f"[REVIEW_{entry_id}_START]\n"
            f"---\n\n"
            f"**Review Date**: {date_str}\n"
            f"**Scope**: {scope}\n"
            f"**Cycle**: {entry_id}\n"
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
            log_path.write_text(existing + "\n" + entry)
        else:
            header = f"# Review Log: {branch}\n\n"
            log_path.write_text(header + entry)

        print(f"[OK] Approved review logged: {log_path} (entry REVIEW_{entry_id})")
        return 0

    branch = get_branch()
    log_dir = Path("./reviews/log")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = get_log_path(branch)

    entry_id = get_next_entry_id(log_path)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Get scope from review file header
    scope = ""
    review_content = Path(review_path).read_text()
    scope_match = re.search(r'\*\*Scope\*\*:\s*(.+)', review_content)
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
            log_path.write_text(existing + "\n" + entry)
        else:
            log_path.write_text(existing + "\n" + entry)
    else:
        header = f"# Review Log: {branch}\n\n"
        log_path.write_text(header + entry)

    print(f"[OK] Review logged: {log_path} (entry REVIEW_{entry_id})")
    return 0


def cmd_validate(log_path: str) -> int:
    p = Path(log_path)
    if not p.exists():
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        return 1

    content = p.read_text()
    errors = []

    # Check header
    if not content.startswith("# Review Log:"):
        errors.append("Missing '# Review Log:' header")

    # Check entry delimiters
    starts = re.findall(r'\[REVIEW_(\d+)_START\]', content)
    ends = re.findall(r'\[REVIEW_(\d+)_END\]', content)

    if not starts:
        errors.append("No review entries found")

    if len(starts) != len(ends):
        errors.append(f"Mismatched delimiters: {len(starts)} START, {len(ends)} END")

    # Check sequential ID ordering
    for i in range(len(starts) - 1):
        if int(starts[i]) >= int(starts[i + 1]):
            errors.append(f"Entry IDs not sequential: REVIEW_{starts[i]} followed by REVIEW_{starts[i+1]}")

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
    next_id = get_next_entry_id(Path(log_path) if log_path else get_log_path())
    print(next_id)
    return 0


def cmd_browse(log_path: str, page: int = 1, per_page: int = 1) -> int:
    p = Path(log_path)
    if not p.exists():
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        return 1

    content = p.read_text()
    entries = re.findall(
        r'\[REVIEW_(\d+)_START\]\n---\n(.*?)\n---\n\[REVIEW_\1_END\]',
        content, re.DOTALL
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
        print(f"{'='*60}")
        print(f"  Entry REVIEW_{eid} ({i+1}/{total})")
        print(f"{'='*60}")
        print(f"\n{body.strip()}\n")

    if end < total:
        print(f"--- Page {page} — use --page {page+1} for next ---")
    else:
        print("--- End of log ---")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Review log management")
    parser.add_argument("--log-create", type=str, default=None,
                        help="Path to review report to log")
    parser.add_argument("--validate", type=str, default=None,
                        help="Validate a review log file")
    parser.add_argument("--next-id", type=str, default=None, const="",
                        nargs="?", help="Get next entry ID for a log (omit path for default)")
    parser.add_argument("--browse", type=str, default=None,
                        help="Browse a review log file")
    parser.add_argument("--page", type=int, default=1,
                        help="Page number for browse (default: 1)")
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
