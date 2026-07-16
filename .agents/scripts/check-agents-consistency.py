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
  6. Implicit rebases — history-moving rebase commands must use ``--onto`` or
     ``--update-refs``
  7. Command dependencies — declared skills and shared command modules must
     exist, and shared modules must have at least two consumers
  8. Command map — every public command appears exactly once and every mapped
     command exists
  9. Skill metadata — every skill has SKILL.md with matching name and a
     nonempty description

Usage:
    uv run python .agents/scripts/check-agents-consistency.py
    uv run python .agents/scripts/check-agents-consistency.py --dir AGENTS.md --dir .agents/commands/
"""

import argparse
import ast
import re
import shlex
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


def _read_error(filepath):
    """Return an error finding when *filepath* cannot be read."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace"):
            return None
    except OSError as exc:
        return SEV_ERR, str(filepath), None, f"Cannot read file: {exc}"


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

    subprocess_methods = {"call", "check_call", "check_output", "Popen", "run"}
    for fp in py_files:
        if fp.name == "gh.py":
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            findings.append((SEV_ERR, str(fp), None, f"Cannot read file: {exc}"))
            continue
        except SyntaxError:
            continue

        module_names = {"subprocess"}
        method_names: set[str] = set()
        process_wrapper_names = {"run_process"}
        cli_common_names = {"cli_common"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "subprocess"
                )
                cli_common_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "cli_common"
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                method_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name in subprocess_methods
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "cli_common":
                process_wrapper_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "run_process"
                )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            is_subprocess = (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in module_names
                and func.attr in subprocess_methods
            ) or (isinstance(func, ast.Name) and func.id in method_names)
            is_process_wrapper = (
                isinstance(func, ast.Name) and func.id in process_wrapper_names
            ) or (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in cli_common_names
                and func.attr == "run_process"
            )
            args = node.args[0]
            if (
                (is_subprocess or is_process_wrapper)
                and isinstance(args, (ast.List, ast.Tuple))
                and args.elts
                and isinstance(args.elts[0], ast.Constant)
                and args.elts[0].value == "gh"
            ):
                findings.append((
                    SEV_ERR, str(fp), node.lineno,
                    "Raw 'gh' subprocess invocation — use gh.py instead",
                ))
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

def check_metadata_source(md_files):
    """Verify that every ``metadata.source`` path points to an existing file."""
    findings: list[Finding] = []

    for fp in md_files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append((SEV_ERR, str(fp), None, f"Cannot read file: {exc}"))
            continue
        front = _extract_frontmatter(content)
        if front is None:
            continue

        lines = front.splitlines()
        metadata_indent = None
        source_indent = None
        source_paths: list[tuple[int, str]] = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if metadata_indent is None:
                if re.fullmatch(r"metadata\s*:\s*(?:#.*)?", stripped):
                    metadata_indent = indent
                continue
            if indent <= metadata_indent:
                metadata_indent = None
                source_indent = None
                continue
            if source_indent is None:
                match = re.fullmatch(r"source\s*:\s*(.*)", stripped)
                if not match:
                    continue
                value = match.group(1).strip()
                if value:
                    source_paths.append((i, value.strip("'\"")))
                else:
                    source_indent = indent
                continue
            if indent <= source_indent:
                source_indent = None
                continue
            match = re.fullmatch(r"-\s+(.+)", stripped)
            if match:
                source_paths.append((i, match.group(1).strip().strip("'\"")))

        for fline, raw_path in source_paths:
            if raw_path.startswith("<") and raw_path.endswith(">"):
                continue
            try:
                path_in_repo = repo_guard.assert_inside_repo(
                    repo_guard.repo_root() / raw_path
                )
            except ValueError:
                findings.append((
                    SEV_ERR, str(fp), fline,
                    f"metadata.source path '{raw_path}' is outside the repository",
                ))
                continue
            if not path_in_repo.exists():
                findings.append((
                    SEV_ERR, str(fp), fline,
                    f"metadata.source path '{raw_path}' does not exist",
                ))
    return findings


# ---------------------------------------------------------------------------
# Check 6: explicit rebase forms
# ---------------------------------------------------------------------------

_REBASE_CONTROL = {"--abort", "--continue", "--skip", "--quit"}
_NON_EXECUTABLE_CONTEXT = re.compile(
    r"\b(?:never|prohibit(?:ed)?|forbid(?:den)?|reject(?:ed)?|invalid)\b", re.I
)


def _implicit_rebase(tokens):
    """Return whether command tokens start an implicit history-moving rebase."""
    if not tokens or tokens[0] != "git":
        return False
    try:
        command_index = next(
            index for index, token in enumerate(tokens[1:], 1) if token in {"pull", "rebase"}
        )
    except StopIteration:
        return False
    command = tokens[command_index]
    arguments = tokens[command_index + 1 :]
    if command == "pull":
        return any(token == "--rebase" or token.startswith("--rebase=") for token in arguments)
    if _REBASE_CONTROL.intersection(arguments):
        return False
    return "--onto" not in arguments and "--update-refs" not in arguments


def _command_tokens(value):
    """Split one documented shell command, returning no tokens on invalid syntax."""
    try:
        tokens = shlex.split(value.lstrip("$ "))
    except ValueError:
        return []
    return tokens


def _python_call_tokens(node):
    """Extract statically visible Git command tokens from one Python call."""
    if not node.args:
        return []
    if isinstance(node.func, ast.Name) and node.func.id == "git":
        values = node.args
        prefix = ["git"]
    elif (
        (
            isinstance(node.func, ast.Name)
            and node.func.id
            in {"run_process", "run", "call", "check_call", "check_output", "Popen"}
        )
        or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {"run", "call", "check_call", "check_output", "Popen"}
        )
    ) and isinstance(node.args[0], (ast.List, ast.Tuple)):
        values = node.args[0].elts
        prefix = []
    else:
        return []
    tokens = [
        value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "<dynamic>"
        for value in values
    ]
    return [*prefix, *tokens]


def check_implicit_rebase(md_files, py_files):
    """Reject executable rebase forms without explicit boundaries or ref updates."""
    findings: list[Finding] = []
    for fp in md_files:
        in_fence = False
        for lineno, line in _read_lines(fp):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if _NON_EXECUTABLE_CONTEXT.search(line):
                continue
            commands = re.findall(r"`([^`]+)`", line)
            if in_fence or stripped.startswith(("git ", "$ git ")):
                commands.append(stripped)
            for command in commands:
                if _implicit_rebase(_command_tokens(command)):
                    findings.append((
                        SEV_ERR,
                        str(fp),
                        lineno,
                        "Implicit rebase — use --onto or --update-refs",
                    ))

    for fp in py_files:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            findings.append((SEV_ERR, str(fp), None, f"Cannot read file: {exc}"))
            continue
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _implicit_rebase(_python_call_tokens(node)):
                findings.append((
                    SEV_ERR,
                    str(fp),
                    node.lineno,
                    "Implicit rebase construction — use --onto or --update-refs",
                ))
    return findings


# ---------------------------------------------------------------------------
# Check 7: command dependencies
# ---------------------------------------------------------------------------

_BACKTICKED_SKILL = re.compile(r"`([a-z][a-z0-9-]*)`")
_COMMON_MODULE = re.compile(r"`(_common-[a-z0-9-]+\.md)`")


def check_command_dependencies(commands_dir, skills_dir):
    """Validate explicit skill and shared-module dependencies in commands."""
    findings: list[Finding] = []
    command_files = sorted(commands_dir.glob("*.md"))
    common_consumers: dict[str, set[Path]] = {}

    for fp in command_files:
        for lineno, line in _read_lines(fp):
            declarations = re.finditer(r"\b(?:load|skills?)\b([^.;:]*)", line, re.I)
            for declaration in declarations:
                for skill in _BACKTICKED_SKILL.findall(declaration.group(1)):
                    if not (skills_dir / skill / "SKILL.md").is_file():
                        findings.append((
                            SEV_ERR,
                            str(fp),
                            lineno,
                            f"Declared skill '{skill}' does not exist",
                        ))

            for module in _COMMON_MODULE.findall(line):
                target = commands_dir / module
                if not target.is_file():
                    findings.append((
                        SEV_ERR,
                        str(fp),
                        lineno,
                        f"Referenced common command module '{module}' does not exist",
                    ))
                elif not fp.name.startswith("_common-"):
                    common_consumers.setdefault(module, set()).add(fp)

    for common in sorted(commands_dir.glob("_common-*.md")):
        consumers = common_consumers.get(common.name, set())
        if len(consumers) < 2:
            findings.append((
                SEV_ERR,
                str(common),
                None,
                f"Common command module must have at least 2 command consumers; "
                f"found {len(consumers)}",
            ))

    return findings


# ---------------------------------------------------------------------------
# Check 8: command map
# ---------------------------------------------------------------------------

_COMMAND_MAP_ROW = re.compile(
    r"^\|\s*`/([a-zA-Z0-9_][a-zA-Z0-9_-]*)`\s*\|"
)


def check_command_map(commands_dir):
    """Validate the canonical public command table in commands/README.md."""
    findings: list[Finding] = []
    readme = commands_dir / "README.md"
    public = {
        fp.stem
        for fp in commands_dir.glob("*.md")
        if fp.name != "README.md" and not fp.name.startswith("_")
    }
    mapped: dict[str, list[int]] = {}

    if not readme.is_file():
        return [(SEV_ERR, str(readme), None, "Canonical command map is missing")]

    for lineno, line in _read_lines(readme):
        match = _COMMAND_MAP_ROW.match(line)
        if match:
            mapped.setdefault(match.group(1), []).append(lineno)

    for command in sorted(public):
        count = len(mapped.get(command, []))
        if count == 0:
            findings.append((
                SEV_ERR, str(readme), None,
                f"Public command '/{command}' is missing from command map",
            ))
        elif count != 1:
            findings.append((
                SEV_ERR, str(readme), mapped[command][1],
                f"Public command '/{command}' appears {count} times in command map",
            ))

    for command, lines in mapped.items():
        if command.startswith("_"):
            findings.append((
                SEV_ERR, str(readme), lines[0],
                f"Command map includes internal command '/{command}'",
            ))
        elif command not in public:
            findings.append((
                SEV_ERR, str(readme), lines[0],
                f"Mapped command '/{command}' has no command file",
            ))
    return findings


# ---------------------------------------------------------------------------
# Check 9: skill metadata
# ---------------------------------------------------------------------------

def check_skills(skills_dir):
    """Validate each direct skill directory and its frontmatter identity."""
    findings: list[Finding] = []
    for skill_dir in sorted(fp for fp in skills_dir.iterdir() if fp.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            findings.append((
                SEV_ERR, str(skill_dir), None,
                f"Skill '{skill_dir.name}' is missing SKILL.md",
            ))
            continue
        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append((SEV_ERR, str(skill_file), None, f"Cannot read file: {exc}"))
            continue
        frontmatter = _extract_frontmatter(content)
        name = re.search(r"^name:\s*(.*?)\s*$", frontmatter or "", re.M)
        description = re.search(
            r"^description:\s*(.*?)\s*$", frontmatter or "", re.M
        )
        actual_name = name.group(1).strip("'\"") if name else ""
        actual_description = description.group(1).strip("'\"") if description else ""
        if actual_name != skill_dir.name:
            findings.append((
                SEV_ERR, str(skill_file), None,
                f"Skill frontmatter name '{actual_name}' does not match directory "
                f"'{skill_dir.name}'",
            ))
        if not actual_description:
            findings.append((
                SEV_ERR, str(skill_file), None,
                "Skill must have a nonempty frontmatter description",
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
    for path in scope:
        try:
            resolved = repo_guard.assert_inside_repo(path)
        except ValueError as exc:
            parser.error(str(exc))
        if not resolved.exists():
            parser.error(f"Path does not exist: {path}")

    md_files = list(_collect_files(scope, ".md"))
    py_files = list(_collect_files(scope, ".py"))
    root = repo_guard.repo_root()
    commands_dir = root / ".agents" / "commands"
    skills_dir = root / ".agents" / "skills"

    all_findings: list[Finding] = []
    unreadable = {
        fp: finding
        for fp in [*md_files, *py_files]
        if (finding := _read_error(fp)) is not None
    }
    all_findings.extend(unreadable.values())
    md_files = [fp for fp in md_files if fp not in unreadable]
    py_files = [fp for fp in py_files if fp not in unreadable]

    if md_files:
        all_findings.extend(check_command_references(md_files, commands_dir))
        all_findings.extend(check_bare_python(md_files))
        all_findings.extend(check_force_push(md_files))
        all_findings.extend(check_metadata_source(md_files))
    if md_files or py_files:
        all_findings.extend(check_raw_gh(md_files, py_files))
        all_findings.extend(check_implicit_rebase(md_files, py_files))
    if not args.dirs:
        all_findings.extend(check_command_dependencies(commands_dir, skills_dir))
        all_findings.extend(check_command_map(commands_dir))
        all_findings.extend(check_skills(skills_dir))

    all_findings.sort(key=lambda x: (x[1], x[2] or 0))

    for severity, path, lineno, msg in all_findings:
        loc = f"{path}:{lineno}" if lineno else path
        print(f"[{severity}] {loc}: {msg}")

    errors = sum(finding[0] == SEV_ERR for finding in all_findings)
    warnings = len(all_findings) - errors
    if all_findings:
        print(
            f"\n{errors} error(s), {warnings} warning(s) found.",
            file=sys.stderr,
        )
    if errors:
        sys.exit(1)
    if warnings:
        sys.exit(0)

    print("No issues found.")
    sys.exit(0)


if __name__ == "__main__":
    main()
