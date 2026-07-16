"""Behavior tests for the technical-debt inventory CLI."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / ".agents/scripts/debt.py"
sys.path.insert(0, str(SCRIPT.parent))


def git(root: Path, *args: str) -> None:
    """Run Git in a disposable repository."""
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def repository(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a repository with the supplied tracked files."""
    git(tmp_path, "init", "-q")
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(tmp_path, "add", ".")
    return tmp_path


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the debt CLI against a disposable repository."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--root", str(root)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_list_reports_stable_markers_in_path_order(tmp_path):
    root = repository(
        tmp_path,
        {
            "src/z.py": (
                "# [DEBT][DEBT-A1B2C3D4]: global lock for now"
                " | trigger: lock contention appears\n"
            ),
            "src/a.ts": (
                "// [DEBT][DEBT-0123ABCD]: linear scan keeps this small"
                " | trigger: collections exceed 1000 items\n"
            ),
            "notes.md": "Example: `[DEBT][DEBT-FFFFFFFF]: not a comment`\n",
        },
    )

    result = run(root, "list", "--format", "json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [record["id"] for record in payload["records"]] == [
        "DEBT-0123ABCD",
        "DEBT-A1B2C3D4",
    ]
    assert payload["summary"] == {"debt": 2, "findings": 0}


def test_check_rejects_malformed_but_allows_shared_debt_ids(tmp_path):
    root = repository(
        tmp_path,
        {
            "a.py": "# [DEBT]: missing stable id | trigger: later\n",
            "b.py": "# [DEBT][DEBT-A1B2C3D4]: first | trigger: later\n",
            "c.py": "# [DEBT][DEBT-A1B2C3D4]: duplicate | trigger: later\n",
        },
    )

    result = run(root, "check", "--format", "json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert [finding["code"] for finding in payload["findings"]] == [
        "MALFORMED_DEBT"
    ]
    assert [record["id"] for record in payload["records"]] == [
        "DEBT-A1B2C3D4",
        "DEBT-A1B2C3D4",
    ]


def test_check_rejects_unrecorded_python_and_javascript_stubs(tmp_path):
    root = repository(
        tmp_path,
        {
            "src/service.py": "def load():\n    raise NotImplementedError\n",
            "src/client.ts": (
                "export function send() {\n"
                "  throw new Error('Not implemented');\n"
                "}\n"
            ),
        },
    )

    result = run(root, "check", "--format", "json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert [finding["code"] for finding in payload["findings"]] == [
        "UNRECORDED_STUB",
        "UNRECORDED_STUB",
    ]


def test_check_accepts_recorded_stub_and_abstract_or_test_placeholders(tmp_path):
    root = repository(
        tmp_path,
        {
            "src/service.py": (
                "# [DEBT][DEBT-A1B2C3D4]: temporary loader stub"
                " | trigger: upstream API is available\n"
                "def load():\n"
                "    raise NotImplementedError\n"
            ),
            "src/interface.py": (
                "from abc import abstractmethod\n\n"
                "@abstractmethod\n"
                "def load():\n"
                "    raise NotImplementedError\n"
            ),
            "tests/test_service.py": "def fake_load():\n    raise NotImplementedError\n",
        },
    )

    result = run(root, "check", "--format", "json")

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["summary"] == {"debt": 1, "findings": 0}


def test_list_uses_only_tracked_text_files(tmp_path):
    root = repository(
        tmp_path,
        {"tracked.py": "# [DEBT][DEBT-A1B2C3D4]: tracked | trigger: later\n"},
    )
    (root / "untracked.py").write_text(
        "# [DEBT][DEBT-0123ABCD]: untracked | trigger: later\n",
        encoding="utf-8",
    )
    (root / "binary.dat").write_bytes(b"\x00# [DEBT][DEBT-FFFFFFFF]: no\n")
    git(root, "add", "binary.dat")

    result = run(root, "list", "--format", "json")

    assert result.returncode == 0
    assert [item["id"] for item in json.loads(result.stdout)["records"]] == [
        "DEBT-A1B2C3D4"
    ]


def test_list_does_not_follow_tracked_symlinks(tmp_path):
    root = repository(tmp_path, {"target.txt": "plain text\n"})
    untracked = root / "untracked.txt"
    untracked.write_text(
        "# [DEBT][DEBT-0123ABCD]: hidden target | trigger: target is tracked\n",
        encoding="utf-8",
    )
    (root / "linked.txt").symlink_to(untracked)
    git(root, "add", "linked.txt")

    result = run(root, "list", "--format", "json")

    assert result.returncode == 0
    assert json.loads(result.stdout)["records"] == []


def test_new_emits_a_well_formed_id_unused_locally_or_remotely(
    tmp_path, monkeypatch, capsys
):
    import debt

    root = repository(tmp_path, {"README.md": "project\n"})
    candidates = iter(("a1b2c3d4", "0123abcd"))
    monkeypatch.setattr(debt.secrets, "token_hex", lambda _size: next(candidates))
    monkeypatch.setattr(
        debt,
        "resolve_debt_issues",
        lambda debt_id, _root: [{"number": 7}] if debt_id == "DEBT-A1B2C3D4" else [],
    )

    code = debt.main(["new", "--format", "json", "--root", str(root)])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["id"] == "DEBT-0123ABCD"


def test_resolve_filters_search_results_to_exact_debt_id(tmp_path, monkeypatch):
    import debt

    root = repository(tmp_path, {"README.md": "project\n"})
    response = json.dumps(
        [
            {
                "number": 7,
                "title": "[Debt][DEBT-A1B2C3D4] Replace stub",
                "body": "Tracked debt.",
                "state": "OPEN",
                "url": "https://example.test/issues/7",
            },
            {
                "number": 8,
                "title": "Unrelated",
                "body": "DEBT-A1B2C3D40 is a different ID",
                "state": "OPEN",
                "url": "https://example.test/issues/8",
            },
        ]
    )
    monkeypatch.setattr(debt, "run_process", lambda *_args, **_kwargs: response)

    assert debt.resolve_debt_issues("DEBT-A1B2C3D4", root) == [
        {
            "number": 7,
            "title": "[Debt][DEBT-A1B2C3D4] Replace stub",
            "body": "Tracked debt.",
            "state": "OPEN",
            "url": "https://example.test/issues/7",
        }
    ]


def test_new_stops_if_remote_uniqueness_cannot_be_checked(
    tmp_path, monkeypatch, capsys
):
    import debt

    root = repository(tmp_path, {"README.md": "project\n"})
    monkeypatch.setattr(
        debt,
        "resolve_debt_issues",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("GitHub unavailable")),
    )

    assert debt.main(["new", "--root", str(root)]) == 3
    assert "GitHub unavailable" in capsys.readouterr().err
