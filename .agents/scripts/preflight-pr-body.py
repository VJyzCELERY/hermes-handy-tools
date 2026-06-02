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

import re
import sys
import argparse
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""


def get_repo_root() -> Path:
    root = run(["git", "rev-parse", "--show-toplevel"])
    if not root:
        print("[WARN] Not inside a git repository.", file=sys.stderr)
        sys.exit(1)
    return Path(root)


def resolve_repo_relative(path_str: str, repo_root: Path) -> str | None:
    raw = Path(path_str)
    if raw.is_absolute():
        resolved = raw
    else:
        try:
            resolved = (Path.cwd() / raw).resolve()
        except Exception:
            return None
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError:
        return None
    return str(relative)


def safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
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


def main():
    parser = argparse.ArgumentParser(description="Pre-flight for PR body generation")
    parser.add_argument("--spec", type=str, required=True, help="Path to spec.md")
    parser.add_argument("--design", type=str, default=None, help="Path to design.md (optional)")
    args = parser.parse_args()

    repo_root = get_repo_root()

    spec_rel = resolve_repo_relative(args.spec, repo_root)
    if not spec_rel or not (repo_root / spec_rel).exists():
        print(f"[WARN] spec.md not found at '{args.spec}'. Cannot extract metadata.", file=sys.stderr)
        spec_rel = spec_rel or args.spec
        feature = ""
        subprojects = ""
        frs = []
    else:
        spec_content = safe_read(repo_root / spec_rel)
        if spec_content is None:
            print(f"[WARN] Could not read spec.md at '{spec_rel}'.", file=sys.stderr)
            feature = ""
            subprojects = ""
            frs = []
        else:
            feature = extract_feature_name(spec_content)
            subprojects = extract_subprojects(spec_content)
            frs = extract_frs(spec_content)

    design_rel = None
    if args.design:
        design_rel = resolve_repo_relative(args.design, repo_root)
        if not design_rel or not (repo_root / design_rel).exists():
            print(f"[WARN] design.md not found at '{args.design}'.", file=sys.stderr)
            design_rel = None
    else:
        auto_design = Path(args.spec).parent / "design.md"
        if auto_design.exists():
            resolved = resolve_repo_relative(str(auto_design), repo_root)
            if resolved:
                design_rel = resolved

    print(f"### Spec / Design References")
    print(f"- **Spec**: `{spec_rel}`")
    if design_rel:
        print(f"- **Design**: `{design_rel}`")

    if feature:
        print(f"\n### Feature")
        print(f"{feature}")

    if subprojects:
        print(f"\n### Subproject(s) Affected")
        print(f"{subprojects}")

    if frs:
        print(f"\n### Functional Requirements")
        for code in frs:
            print(f"- {code}")


if __name__ == "__main__":
    main()
