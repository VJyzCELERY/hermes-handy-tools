"""Strict parsing and lifecycle state for canonical review reports."""

import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import repo_guard


FINDING_ID = r"[A-Z][A-Z0-9]*-[A-Z][A-Z0-9]*-\d{3}"
STATUSES = {"OPEN", "ADDRESSED", "INVALID", "DEFERRED"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
FIELDS = {
    "Status",
    "Severity",
    "Category",
    "Location",
    "Description",
    "Why It Matters",
    "Suggested Fix",
    "How to Validate",
    "Expected Addressed Result",
}


def _section(content: str, heading: str) -> str:
    matches = list(re.finditer(rf"^## {re.escape(heading)}\s*$", content, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"Malformed review: expected exactly one ## {heading} section")
    start = matches[0].end()
    end = re.search(r"^##\s", content[start:], re.MULTILINE)
    return content[start : start + end.start() if end else None].strip()


def parse_findings(content: str) -> list[dict]:
    """Parse the canonical strict findings schema used by review-log.py."""
    section = re.sub(
        r"(?:^|\n)---\s*$", "", _section(content, "Findings"), flags=re.MULTILINE
    ).strip()
    if section == "No findings.":
        return []
    if not section.startswith("### "):
        raise ValueError("Malformed review: use 'No findings.' for a clean report")

    findings = []
    for block in filter(str.strip, re.split(r"(?=^### )", section, flags=re.MULTILINE)):
        header = re.match(
            rf"^### \[({FINDING_ID})\] - \[([A-Z]+)\] - (\S.+)$", block, re.MULTILINE
        )
        if not header:
            raise ValueError("Malformed review finding: invalid heading")
        finding_id, heading_severity, title = header.groups()
        labels = re.findall(r"^\*\*([^*]+)\*\*:", block, re.MULTILINE)
        if len(labels) != len(FIELDS) or set(labels) != FIELDS:
            raise ValueError(f"Malformed review finding {finding_id}: invalid fields")

        values = {}
        for field in ("Status", "Severity", "Category", "Location"):
            match = re.search(rf"^\*\*{field}\*\*:\s*(\S.*)$", block, re.MULTILINE)
            if not match:
                raise ValueError(
                    f"Malformed review finding {finding_id}: missing {field}"
                )
            values[field] = match.group(1).strip()
        text_values = {}
        for field in (
            "Description",
            "Why It Matters",
            "Suggested Fix",
            "Expected Addressed Result",
        ):
            match = re.search(
                rf"^\*\*{field}\*\*:\s*\n(.+?)(?=\n\n\*\*|\Z)",
                block,
                re.MULTILINE | re.DOTALL,
            )
            if not match or not match.group(1).strip():
                raise ValueError(
                    f"Malformed review finding {finding_id}: missing {field}"
                )
            text_values[field] = match.group(1).strip()
        validation = re.search(
            r"^\*\*How to Validate\*\*:\s*\n```(?:bash|sh)\n(.+?)\n```",
            block,
            re.MULTILINE | re.DOTALL,
        )
        if not validation or not any(
            line.strip() and not line.lstrip().startswith("#")
            for line in validation.group(1).splitlines()
        ):
            raise ValueError(
                f"Malformed review finding {finding_id}: missing runnable How to Validate"
            )
        if values["Status"] not in STATUSES:
            raise ValueError(f"Malformed review finding {finding_id}: invalid Status")
        if (
            values["Severity"] not in SEVERITIES
            or values["Severity"] != heading_severity
        ):
            raise ValueError(f"Malformed review finding {finding_id}: invalid Severity")
        if values["Category"] != finding_id.split("-", 1)[0]:
            raise ValueError(
                f"Malformed review finding {finding_id}: Category does not match ID"
            )
        findings.append(
            {
                "id": finding_id,
                "title": title,
                "status": values["Status"].lower(),
                "severity": values["Severity"].lower(),
                "category": values["Category"].lower(),
                "location": values["Location"],
                "problem": text_values["Description"],
                "impact": text_values["Why It Matters"],
                "resolution": text_values["Suggested Fix"],
                "validation": validation.group(1).strip(),
                "expected_result": text_values["Expected Addressed Result"],
                "reasoning": "",
            }
        )
    return findings


def parse_remote_feedback(content: str):
    """Return structured remote feedback, or UNLINKED for legacy reports."""
    headings = list(re.finditer(r"^## Remote Feedback\s*$", content, re.MULTILINE))
    if not headings:
        return "UNLINKED"
    if len(headings) != 1:
        raise ValueError("Malformed Remote Feedback: expected one section")
    section = _section(content, "Remote Feedback")
    if section == "UNLINKED":
        return "UNLINKED"
    match = re.fullmatch(r"```json\s*\n(.+?)\n```", section, re.DOTALL)
    if not match:
        raise ValueError("Malformed Remote Feedback: expected a JSON fence")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed Remote Feedback JSON: {error}") from error
    required = {"repository", "pull_request", "head", "items"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Malformed Remote Feedback schema")
    repository = payload["repository"]
    pull_request = payload["pull_request"]
    if not all(
        isinstance(payload[key], str) for key in ("repository", "pull_request", "head")
    ):
        raise ValueError("Malformed Remote Feedback schema")
    if not re.fullmatch(r"https://github\.com/[^/]+/[^/#]+", repository):
        raise ValueError("Malformed Remote Feedback repository URL")
    if not re.fullmatch(rf"{re.escape(repository)}/pull/[1-9]\d*", pull_request):
        raise ValueError("Malformed Remote Feedback pull request URL")
    if not re.fullmatch(r"[0-9a-f]{40}", payload["head"]):
        raise ValueError("Malformed Remote Feedback head")
    if not isinstance(payload["items"], list):
        raise ValueError("Malformed Remote Feedback schema")
    urls = set()
    for item in payload["items"]:
        if not isinstance(item, dict) or set(item) != {"url", "reply"}:
            raise ValueError("Malformed Remote Feedback item")
        if not isinstance(item["url"], str) or not isinstance(item["reply"], str):
            raise ValueError("Malformed Remote Feedback item")
        parsed = urlsplit(item["url"])
        if (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}" != pull_request
            or parsed.query
            or not re.fullmatch(
                r"(?:discussion_r\d+|pullrequestreview-\d+)", parsed.fragment
            )
            or item["url"] in urls
        ):
            raise ValueError("Malformed Remote Feedback item URL")
        urls.add(item["url"])
    return payload


def read_report(path: Path | str) -> dict:
    """Read and strictly parse a review report."""
    path = repo_guard.assert_inside_repo(path)
    content = path.read_text(encoding="utf-8")
    range_match = re.search(
        r"\*{0,2}Commit Range\*{0,2}:\s*`?([0-9a-f]+)`?\s*\.\.\.\s*`?([0-9a-f]+)`?",
        content,
    )
    if (
        not re.search(r"^# Review Report:\s*\S", content, re.MULTILINE)
        or not range_match
    ):
        raise ValueError("Malformed review header")
    branch_match = re.search(r"\*{0,2}Branch\*{0,2}:\s*(\S.+)$", content, re.MULTILINE)
    if not branch_match:
        raise ValueError("Malformed review header: missing Branch")
    return {
        "base": range_match.group(1),
        "head": range_match.group(2),
        "branch": branch_match.group(1).strip(),
        "findings": parse_findings(content),
        "remote_feedback": parse_remote_feedback(content),
    }


def classify_report(path: Path | str, current_head: str | None = None) -> dict:
    """Classify a report without raising for malformed or absent files."""
    path = repo_guard.assert_inside_repo(path)
    if not path.exists():
        return {"state": "ABSENT", "path": str(path)}
    archives = repo_guard.repo_root() / "reviews" / "archives"
    if path.is_relative_to(archives.resolve()):
        return {"state": "ARCHIVED", "path": str(path)}
    try:
        report = read_report(path)
    except (OSError, UnicodeError, ValueError) as error:
        return {"state": "MALFORMED", "path": str(path), "error": str(error)}
    if current_head and report["head"] != current_head:
        state = "STALE"
    elif not report["findings"]:
        state = "CLEAN"
    elif any(item["status"] == "open" for item in report["findings"]):
        state = "ACTIVE_OPEN"
    else:
        state = "COMPLETE"
    return {"state": state, "path": str(path), **report}


def write_atomic(path: Path | str, content: str) -> None:
    """Atomically replace a UTF-8 file in its destination directory."""
    path = repo_guard.assert_inside_repo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
