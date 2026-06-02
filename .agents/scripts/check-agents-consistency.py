#!/usr/bin/env python3
"""Validate agent instruction files for consistency and safety issues.

Checks:
  1. Stale command references — mentions of /cmds or .agents/commands/ files
     that don't exist
  2. Raw ``gh`` CLI usage — lines that invoke the ``gh`` binary directly
     instead of ``gh.py``
  3. Bare ``python`` / ``pytest`` — invocations not preceded by ``uv run``
  4. ``git push --force`` — bare force push without ``--with-lease``
  5. ``metadata.source`` path validation — YAML frontmatter entries pointing
     to nonexistent files

Usage:
    uv run python .agents/scripts/check-agents-consistency.py
    uv run python .agents/scripts/check-agents-consistency.py --dir AGENTS.md --dir .agents/commands/
"""

import argparse
import re
import sys
from pathlib import Path

import repo_guard

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

Finding = tuple[str, str, int | None, str]
SEV_ERR = "ERR"
SEV_WARN = "WARN"


def _collect_files(scope_paths, *extensions):
    """Yield every file under *scope_paths* whose suffix is in *extensions*."""
    seen: set[str] = set()
    exclude_dirs = {"node_modules", "__pycache__", ".git"}

    for raw in scope_paths:
        resolved = repo_guard.assert_inside_repo(raw)
        if resolved.is_dir():
            for ext in extensions:
                for fp in sorted(resolved.rglob(f"*{ext}")):
                    if any(p.name in exclude_dirs for p in fp.parents):
                        continue
                    if str(fp) not in seen:
                        seen.add(str(fp))
                        yield fp
        elif resolved.is_file() and resolved.suffix in extensions:
            if str(resolved) not in seen:
                seen.add(str(resolved))
                yield resolved


def _read_lines(filepath):
    """Return list of ``(line_number, text)``."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return [(i + 1, line.rstrip("\n\r")) for i, line in enumerate(f)]
    except OSError as exc:
        print(f"[WARN] Skipping unreadable file {filepath}: {exc}", file=sys.stderr)
        return []


def _extract_frontmatter(content):
    """Return raw frontmatter text (between --- markers) or None."""
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    return content[3:end]


# ---------------------------------------------------------------------------
# Check 1: command-reference staleness
# ---------------------------------------------------------------------------

def check_command_references(md_files, commands_dir):
    """Report mentions of commands whose files don't exist.

    Only checks inline-code mentions (`` `/cmd` ``) and explicit paths
    (``.agents/commands/name.md``) to avoid noise from HTML tags and
    URL path components.
    """
    findings: list[Finding] = []
    existing = {f.stem for f in commands_dir.glob("*.md")} if commands_dir.is_dir() else set()

    slash_inline = re.compile(r"`/([a-z][a-z0-9-]*[a-z0-9])`")
    path_ref = re.compile(r"\.agents/commands/([a-zA-Z0-9_][a-zA-Z0-9_-]*)\.md")

    for fp in md_files:
        for lineno, line in _read_lines(fp):
            for m in slash_inline.finditer(line):
                name = m.group(1)
                if name not in existing:
                    findings.append((
                        SEV_WARN, str(fp), lineno,
                        f"References nonexistent command '/{name}'",
                    ))
            for m in path_ref.finditer(line):
                name = m.group(1)
                if name not in existing:
                    findings.append((
                        SEV_ERR, str(fp), lineno,
                        f"References nonexistent command file '.agents/commands/{name}.md'",
                    ))
    return findings


# ---------------------------------------------------------------------------
# Check 2: raw ``gh`` usage
# ---------------------------------------------------------------------------

GH_INLINE_PATTERN = re.compile(r"`gh (?!py\b)(\w+)")


def check_raw_gh(md_files, py_files):
    """Report lines that invoke raw ``gh`` CLI (not ``gh.py``)."""
    findings: list[Finding] = []

    for fp in md_files:
        for lineno, line in _read_lines(fp):
            for m in GH_INLINE_PATTERN.finditer(line):
                cmd = m.group(1)
                findings.append((
                    SEV_ERR, str(fp), lineno,
                    f"Raw 'gh {cmd}' — use 'gh.py cmd {cmd}' instead",
                ))

    for fp in py_files:
        for lineno, line in _read_lines(fp):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Look for string literals containing "gh " (not "gh.py ")
            for match in re.finditer(r"""(["'])(gh\s+\S)""", line):
                val = match.group(2)
                if val.startswith("gh ") and "gh.py" not in line:
                    findings.append((
                        SEV_ERR, str(fp), lineno,
                        f"Raw 'gh' invocation pattern in Python source: {val!r}",
                    ))
                    break
    return findings


# ---------------------------------------------------------------------------
# Check 3: bare ``python`` / ``pytest``
# ---------------------------------------------------------------------------

# English words that follow "python" / "pytest" in prose (not as a command).
_PROSE_FOLLOWERS = frozenset({
    "with", "for", "and", "the", "in", "is", "are", "can", "will",
    "should", "may", "must", "not", "or", "to", "of", "using", "on",
    "by", "as", "at", "from", "code", "script", "module", "library",
})


def check_bare_python(md_files):
    """Report ``python`` / ``pytest`` not preceded by ``uv run``.

    Only flags actual command invocations (inside inline code, after a
    pipe, or on a standalone command line) — not prose or code-fence
    language identifiers.
    """
    findings: list[Finding] = []
    fence_re = re.compile(r"^`{3,}\s*(python|python3|pytest)\s*$")

    for fp in md_files:
        lines = _read_lines(fp)

        for lineno, line in lines:
            if "uv run" in line:
                continue

            # skip code-fence lines: ```python, ```pytest
            if fence_re.match(line):
                continue

            # inline-code check: `` `python -c ...` ``  or  `` `pytest tests/` ``
            # Must start with python/pytest (possibly after $ or whitespace)
            # so `` `@pytest.mark.skip` `` does NOT match.
            if re.search(r"`\s*(?:\$\s*)?(python|python3|pytest)\s", line):
                findings.append((
                    SEV_WARN, str(fp), lineno,
                    "Bare python/pytest in inline code — prefix with 'uv run'",
                ))
                continue

            # pipe chain:  | python, ; python, && python
            if re.search(r"(?:^|[|;&])\s*(python|python3|pytest)\s", line):
                findings.append((
                    SEV_WARN, str(fp), lineno,
                    "Bare python/pytest after pipe/separator — prefix with 'uv run'",
                ))
                continue

            # standalone command at line start (not inside a python code block):
            #   python -c, pytest tests/, python3 script.py
            prefix = re.search(r"^\s*(python|python3|pytest)\s+", line)
            if prefix:
                cmd = prefix.group(1)
                rest = line[prefix.end():].lstrip()
                next_word = rest.split()[0] if rest else ""
                if next_word and next_word not in _PROSE_FOLLOWERS:
                    findings.append((
                        SEV_WARN, str(fp), lineno,
                        f"Bare '{cmd}' — prefix with 'uv run'",
                    ))
    return findings


# ---------------------------------------------------------------------------
# Check 4: force-push detection
# ---------------------------------------------------------------------------

FORCE_PUSH = re.compile(r"\bgit push --force\b(?!-with-lease)")


def check_force_push(md_files):
    """Report bare ``git push --force`` (not ``--force-with-lease``)."""
    findings: list[Finding] = []

    for fp in md_files:
        for lineno, line in _read_lines(fp):
            if FORCE_PUSH.search(line):
                findings.append((
                    SEV_ERR, str(fp), lineno,
                    "Use 'git push --force-with-lease' instead of 'git push --force'",
                ))
    return findings


# ---------------------------------------------------------------------------
# Check 5: ``metadata.source`` path validation
# ---------------------------------------------------------------------------

META_SOURCE_ITEM = re.compile(r"^\s{4}source:\s+(.+)$")
META_SOURCE_LIST = re.compile(r"^\s{6}-\s+(.+)$")


def check_metadata_source(md_files):
    """Verify that every ``metadata.source`` path points to an existing file."""
    findings: list[Finding] = []

    for fp in md_files:
        content = fp.read_text(encoding="utf-8", errors="replace")
        front = _extract_frontmatter(content)
        if front is None:
            continue

        lines = front.splitlines()
        in_metadata = False
        source_paths: list[tuple[int, str]] = []

        for i, line in enumerate(lines):
            stripped = line.rstrip()
            if stripped == "metadata:" or stripped.startswith("metadata:"):
                in_metadata = True
                continue
            if in_metadata and re.match(r"^\s{2}[a-z]", stripped):
                in_metadata = False
            if in_metadata:
                m = META_SOURCE_ITEM.match(stripped)
                if m:
                    source_paths.append((i + 1, m.group(1).strip()))
                m2 = META_SOURCE_LIST.match(stripped)
                if m2:
                    source_paths.append((i + 1, m2.group(1).strip()))

        for fline, raw_path in source_paths:
            path_in_repo = repo_guard.repo_root() / raw_path
            if not path_in_repo.exists():
                findings.append((
                    SEV_ERR, str(fp), fline,
                    f"metadata.source path '{raw_path}' does not exist",
                ))
    return findings


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _resolve_default_scope():
    root = repo_guard.repo_root()
    result = []
    agents_dir = root / ".agents"
    if agents_dir.is_dir():
        result.append(agents_dir)
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        result.append(agents_md)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Check agent instructions consistency",
    )
    parser.add_argument(
        "--dir",
        action="append",
        dest="dirs",
        default=[],
        help="Path to scan (file or directory, repeatable; default: .agents/ and AGENTS.md)",
    )
    args = parser.parse_args()

    scope = [Path(p) for p in (args.dirs if args.dirs else _resolve_default_scope())]

    repo_guard.assert_inside_repo(scope[0])

    md_files = list(_collect_files(scope, ".md"))
    py_files = list(_collect_files(scope, ".py"))
    root = repo_guard.repo_root()
    commands_dir = root / ".agents" / "commands"

    all_findings: list[Finding] = []

    if md_files:
        all_findings.extend(check_command_references(md_files, commands_dir))
        all_findings.extend(check_bare_python(md_files))
        all_findings.extend(check_force_push(md_files))
        all_findings.extend(check_metadata_source(md_files))
    if md_files or py_files:
        all_findings.extend(check_raw_gh(md_files, py_files))

    all_findings.sort(key=lambda x: (x[1], x[2] or 0))

    for severity, path, lineno, msg in all_findings:
        loc = f"{path}:{lineno}" if lineno else path
        print(f"[{severity}] {loc}: {msg}")

    if all_findings:
        print(f"\n{len(all_findings)} issue(s) found.", file=sys.stderr)
        sys.exit(1)

    print("No issues found.")
    sys.exit(0)


if __name__ == "__main__":
    main()
