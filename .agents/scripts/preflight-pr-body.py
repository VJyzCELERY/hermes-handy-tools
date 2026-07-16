"""Pre-flight for PR body generation — resolves spec/design paths to repo-root-relative.

Usage:
    uv run python .agents/scripts/preflight-pr-body.py --spec <path> [--design <path>]

Given a spec.md (and optionally design.md), outputs:
- Repo-root-relative paths (handles worktrees — never prefixes .worktrees/...)
- Feature name extracted from the spec heading
- Subproject(s) extracted from the spec metadata
- Functional requirement codes extracted from the spec

Path resolution: absolute, CWD-relative, and worktree-relative paths all work.
The output path is always relative to `git rev-parse --show-toplevel`.

Graceful failure: if spec or design file doesn't exist, prints a warning and
skips extraction rather than crashing.
<EOF_DESC>
"""

import argparse
import re
import sys
from pathlib import Path

import repo_guard
from cli_common import EXIT_EXTERNAL, EXIT_FAILURE, ExternalCommandError, run_process


def get_repo_root() -> Path:
    root = run_process(["git", "rev-parse", "--show-toplevel"])
    if not root:
        raise ValueError("Git did not return a repository root.")
    return repo_guard.assert_inside_repo(root)


def resolve_repo_relative(path_str: str, repo_root: Path) -> str | None:
    raw = Path(path_str)
    candidate = raw if raw.is_absolute() else Path.cwd() / raw
    try:
        resolved = repo_guard.assert_inside_repo(candidate)
        relative = resolved.relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return str(relative)


def safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def extract_feature_name(content: str) -> str:
    m = re.search(r'^# Feature Specification:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r'^# Design Document:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def extract_subprojects(content: str) -> str:
    m = re.search(r'^\*\*Subproject\(s\) Affected\*\*:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def extract_frs(content: str) -> list[str]:
    codes = []
    for m in re.finditer(r'^\s*-\s+\*\*(FR-\d+)\*\*', content, re.MULTILINE):
        codes.append(m.group(1))
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight for PR body generation")
    parser.add_argument("spec_path", nargs="?", help="Path to spec.md")
    parser.add_argument("--spec", dest="spec_option", help="Path to spec.md")
    parser.add_argument("--design", help="Path to design.md (optional)")
    args = parser.parse_args()
    if args.spec_path and args.spec_option:
        parser.error("provide the spec using either the positional argument or --spec")
    spec_path = args.spec_path or args.spec_option
    if not spec_path:
        parser.error("a spec path is required")

    try:
        repo_root = get_repo_root()
    except ExternalCommandError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[FAIL] Invalid repository root: {error}", file=sys.stderr)
        return EXIT_FAILURE

    spec_rel = resolve_repo_relative(spec_path, repo_root)
    if spec_rel is None:
        print(f"[FAIL] Spec path '{spec_path}' is outside the repository.", file=sys.stderr)
        return EXIT_FAILURE
    spec_file = repo_root / spec_rel
    if not spec_file.is_file():
        print(f"[FAIL] spec.md not found at '{spec_path}'.", file=sys.stderr)
        return EXIT_FAILURE
    spec_content = safe_read(spec_file)
    if spec_content is None:
        print(f"[FAIL] Could not read spec.md at '{spec_rel}'.", file=sys.stderr)
        return EXIT_FAILURE

    design_rel = None
    if args.design:
        design_rel = resolve_repo_relative(args.design, repo_root)
        if design_rel is None:
            print(
                f"[FAIL] Design path '{args.design}' is outside the repository.",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        if not (repo_root / design_rel).is_file():
            print(f"[FAIL] design.md not found at '{args.design}'.", file=sys.stderr)
            return EXIT_FAILURE
    else:
        auto_design = spec_file.parent / "design.md"
        if auto_design.exists() or auto_design.is_symlink():
            resolved = resolve_repo_relative(str(auto_design), repo_root)
            if resolved is None:
                print(
                    f"[FAIL] Design path '{auto_design}' is outside the repository.",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
            design_rel = resolved

    feature = extract_feature_name(spec_content)
    subprojects = extract_subprojects(spec_content)
    frs = extract_frs(spec_content)

    print("### Spec / Design References")
    print(f"- **Spec**: `{spec_rel}`")
    if design_rel:
        print(f"- **Design**: `{design_rel}`")

    if feature:
        print("\n### Feature")
        print(feature)

    if subprojects:
        print("\n### Subproject(s) Affected")
        print(subprojects)

    if frs:
        print("\n### Functional Requirements")
        for code in frs:
            print(f"- {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
