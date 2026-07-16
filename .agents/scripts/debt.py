#!/usr/bin/env python3
"""Generate, inventory, validate, and resolve stable technical-debt IDs."""

from __future__ import annotations

import argparse
import ast
import json
import re
import secrets
import sys
from pathlib import Path

import repo_guard
from cli_common import EXIT_EXTERNAL, EXIT_FAILURE, ExternalCommandError, run_process


DEBT_ID = re.compile(r"DEBT-[0-9A-F]{8}")
COMMENT_DEBT = re.compile(r"^\s*(?:#|//|--|/\*+|\*|<!--)\s*\[DEBT\]")
MARKER = re.compile(
    r"^\s*(?:#|//|--|/\*+|\*|<!--)\s*"
    r"\[DEBT\]\[(DEBT-[0-9A-F]{8})\]:\s*(.+?)\s*"
    r"\|\s*trigger:\s*(.+?)(?:\s*(?:\*/|-->)\s*)?$"
)
JS_STUB = re.compile(
    r"throw\s+new\s+Error\s*\(\s*['\"]not implemented(?: yet)?['\"]\s*\)",
    re.IGNORECASE,
)


def tracked_files(root: Path) -> list[Path]:
    """Return sorted Git-tracked paths below *root*."""
    output = run_process(["git", "-C", str(root), "ls-files", "-z"], cwd=root)
    return [root / name for name in sorted(filter(None, output.split("\0")))]


def _text(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        content = path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"Cannot read {path}: {error}") from error
    if b"\0" in content:
        return None
    return content.decode("utf-8", errors="replace")


def _record(path: str, line: int, match: re.Match[str]) -> dict:
    return {
        "id": match.group(1),
        "path": path,
        "line": line,
        "reason": match.group(2).strip(),
        "trigger": match.group(3).strip(),
    }


def _finding(code: str, path: str, line: int, message: str) -> dict:
    return {"code": code, "path": path, "line": line, "message": message}


def _is_test(path: Path) -> bool:
    return path.name.startswith("test_") or "tests" in path.parts


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_stub_statement(node: ast.stmt) -> bool:
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return node.value.value is Ellipsis
    if not isinstance(node, ast.Raise) or node.exc is None:
        return False
    called = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    return isinstance(called, ast.Name) and called.id == "NotImplementedError"


def _python_stub_lines(text: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    stubs: list[tuple[int, int]] = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, functions):
            continue
        if any(_decorator_name(item) == "abstractmethod" for item in node.decorator_list):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.ClassDef):
            bases = {_decorator_name(base) for base in parent.bases}
            if bases & {"ABC", "Protocol"}:
                continue
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
        if len(body) == 1 and _is_stub_statement(body[0]):
            stubs.append((node.lineno, body[0].lineno))
    return stubs


def _has_nearby_debt(marker_lines: set[int], start: int, stub: int) -> bool:
    return any(line in marker_lines for line in range(max(1, start - 2), stub + 1))


def scan(root: Path) -> tuple[list[dict], list[dict]]:
    """Return debt records and local validation findings."""
    records: list[dict] = []
    findings: list[dict] = []
    for path in tracked_files(root):
        text = _text(path)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        lines = text.splitlines()
        marker_lines: set[int] = set()
        for number, line in enumerate(lines, 1):
            match = MARKER.match(line)
            if match:
                records.append(_record(relative, number, match))
                marker_lines.add(number)
            elif COMMENT_DEBT.match(line):
                findings.append(
                    _finding(
                        "MALFORMED_DEBT",
                        relative,
                        number,
                        "Use [DEBT][DEBT-XXXXXXXX]: reason | trigger: condition",
                    )
                )

        if _is_test(path):
            continue
        if path.suffix == ".py":
            for start, stub in _python_stub_lines(text):
                if not _has_nearby_debt(marker_lines, start, stub):
                    findings.append(
                        _finding(
                            "UNRECORDED_STUB",
                            relative,
                            stub,
                            "Production stub requires an explanatory debt marker",
                        )
                    )
        elif path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            for number, line in enumerate(lines, 1):
                if JS_STUB.search(line) and not _has_nearby_debt(
                    marker_lines, number, number
                ):
                    findings.append(
                        _finding(
                            "UNRECORDED_STUB",
                            relative,
                            number,
                            "Production stub requires an explanatory debt marker",
                        )
                    )
    records.sort(key=lambda item: (item["path"], item["line"]))
    findings.sort(key=lambda item: (item["path"], item["line"], item["code"]))
    return records, findings


def resolve_debt_issues(debt_id: str, root: Path) -> list[dict]:
    """Return GitHub issues that contain the exact stable debt ID."""
    gh_script = Path(__file__).with_name("gh.py")
    output = run_process(
        [
            sys.executable,
            str(gh_script),
            "cmd",
            "--format",
            "json",
            "issue",
            "list",
            "--state",
            "all",
            "--search",
            debt_id,
            "--limit",
            "100",
            "--json",
            "number,title,body,state,url",
        ],
        cwd=root,
    )
    issues = json.loads(output or "[]")
    exact = re.compile(rf"(?<![A-Z0-9-]){re.escape(debt_id)}(?![A-Z0-9-])")
    return [
        issue
        for issue in issues
        if exact.search(f"{issue.get('title', '')}\n{issue.get('body') or ''}")
    ]


def _payload(records: list[dict], findings: list[dict]) -> dict:
    return {
        "records": records,
        "findings": findings,
        "summary": {"debt": len(records), "findings": len(findings)},
    }


def _print(payload: dict, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for record in payload.get("records", []):
        print(
            f"{record['id']} {record['path']}:{record['line']} "
            f"{record['reason']} | trigger: {record['trigger']}"
        )
    for finding in payload.get("findings", []):
        print(
            f"{finding['code']} {finding['path']}:{finding['line']} "
            f"{finding['message']}"
        )
    summary = payload.get("summary")
    if summary:
        print(f"Debt: {summary['debt']}; findings: {summary['findings']}")


def _root(value: str) -> Path:
    return repo_guard.assert_inside_repo(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("new", "list", "check"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", default=str(repo_guard.repo_root()), type=_root)
        command.add_argument("--format", choices=("text", "json"), default="text")
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("debt_id")
    resolve.add_argument("--root", default=str(repo_guard.repo_root()), type=_root)
    resolve.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the debt command-line interface."""
    args = _parser().parse_args(argv)
    try:
        records, findings = scan(args.root)
        if args.command in {"list", "check"}:
            _print(_payload(records, findings), args.format)
            return EXIT_FAILURE if args.command == "check" and findings else 0
        if args.command == "resolve":
            if not DEBT_ID.fullmatch(args.debt_id):
                raise ValueError("Debt ID must match DEBT-XXXXXXXX (uppercase hex)")
            issues = resolve_debt_issues(args.debt_id, args.root)
            payload = {"id": args.debt_id, "issues": issues, "count": len(issues)}
            print(json.dumps(payload, indent=2, sort_keys=True) if args.format == "json" else payload)
            return 0

        used = {record["id"] for record in records}
        for _attempt in range(100):
            debt_id = f"DEBT-{secrets.token_hex(4).upper()}"
            if debt_id not in used and not resolve_debt_issues(debt_id, args.root):
                payload = {"id": debt_id}
                print(json.dumps(payload) if args.format == "json" else debt_id)
                return 0
        raise RuntimeError("Could not generate an unused debt ID")
    except (ExternalCommandError, json.JSONDecodeError, OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
