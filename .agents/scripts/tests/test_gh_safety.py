"""Focused safety and output-contract tests for gh.py."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import gh


ROOT = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp"


def test_import_does_not_create_directories(monkeypatch):
    calls = []
    original_mkdir = Path.mkdir

    def record_mkdir(self, *args, **kwargs):
        calls.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", record_mkdir)
    spec = importlib.util.spec_from_file_location("gh_import_check", gh.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert calls == []


def test_clean_temp_only_deletes_regular_files_under_repo_tmp():
    temporary = TMP / "gh-safety-delete-me.txt"
    caller_owned = ROOT / ".agents" / "local" / "gh-safety-keep-me.txt"
    caller_owned.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text("temporary")
    caller_owned.write_text("owned by caller")
    try:
        gh.clean_temp(temporary)
        gh.clean_temp(caller_owned)

        assert not temporary.exists()
        assert caller_owned.read_text() == "owned by caller"
    finally:
        temporary.unlink(missing_ok=True)
        caller_owned.unlink(missing_ok=True)


def test_check_file_requires_regular_nonempty_file(capsys):
    regular = TMP / "gh-safety-input.txt"
    empty = TMP / "gh-safety-empty.txt"
    directory = TMP / "gh-safety-directory"
    regular.write_text("content")
    empty.touch()
    directory.mkdir(exist_ok=True)
    try:
        assert gh.check_file(str(regular))
        assert not gh.check_file(str(empty))
        assert not gh.check_file(str(directory))
        assert "regular file" in capsys.readouterr().err
    finally:
        regular.unlink(missing_ok=True)
        empty.unlink(missing_ok=True)
        directory.rmdir()


def test_generated_payloads_create_tmp_lazily_and_use_unique_names(monkeypatch):
    generated_tmp = TMP / "gh-safety-generated"
    body_file = ROOT / ".agents" / "local" / "gh-safety-reply.md"
    body_file.parent.mkdir(parents=True, exist_ok=True)
    body_file.write_text("reply")
    payload_paths = []

    def capture_run(command, *args, **kwargs):
        payload_path = Path(command[command.index("--input") + 1])
        assert payload_path.is_file()
        payload_paths.append(payload_path)
        return "{}", "", 0

    monkeypatch.setattr(gh, "TMP_DIR", generated_tmp)
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "run", capture_run)
    args = argparse.Namespace(pr_or_url="7", comment_id="11", body_file=str(body_file))
    try:
        assert not generated_tmp.exists()

        gh.cmd_reply_comment(args)
        gh.cmd_reply_comment(args)

        assert generated_tmp.is_dir()
        assert len(set(payload_paths)) == 2
        assert all(not path.exists() for path in payload_paths)
        assert body_file.read_text() == "reply"
    finally:
        body_file.unlink(missing_ok=True)
        for path in generated_tmp.glob("*") if generated_tmp.exists() else []:
            path.unlink()
        if generated_tmp.exists():
            generated_tmp.rmdir()


@pytest.mark.parametrize("failure_stage", ["metadata", "api", "unexpected"])
def test_generated_payload_is_cleaned_after_mutation_failure(
    monkeypatch, failure_stage
):
    generated_tmp = TMP / f"gh-safety-{failure_stage}"
    body_file = ROOT / ".agents" / "local" / f"gh-safety-{failure_stage}.md"
    body_file.parent.mkdir(parents=True, exist_ok=True)
    body_file.write_text("reply")

    def fail_metadata():
        raise RuntimeError("metadata failed")

    def fail_api(*args, **kwargs):
        if failure_stage == "unexpected":
            raise RuntimeError("unexpected failure")
        return "", "api failed", 1

    monkeypatch.setattr(gh, "TMP_DIR", generated_tmp)
    monkeypatch.setattr(
        gh,
        "get_owner_repo",
        fail_metadata if failure_stage == "metadata" else lambda: "acme/widgets",
    )
    monkeypatch.setattr(gh, "run", fail_api)
    args = argparse.Namespace(pr_or_url="7", comment_id="11", body_file=str(body_file))
    expected_error = SystemExit if failure_stage == "api" else RuntimeError
    try:
        with pytest.raises(expected_error):
            gh.cmd_reply_comment(args)

        assert generated_tmp.is_dir()
        assert list(generated_tmp.iterdir()) == []
        assert body_file.read_text() == "reply"
    finally:
        body_file.unlink(missing_ok=True)
        for path in generated_tmp.glob("*") if generated_tmp.exists() else []:
            path.unlink()
        if generated_tmp.exists():
            generated_tmp.rmdir()


def test_successful_mutation_does_not_delete_caller_file_in_tmp(monkeypatch):
    body_file = TMP / "gh-safety-caller-owned.md"
    body_file.write_text("caller owned")
    monkeypatch.setattr(gh, "api", lambda *args, **kwargs: ("{}", "", 0))
    args = argparse.Namespace(pr_or_url="7", body_file=str(body_file))
    try:
        gh.cmd_post_comment(args)

        assert body_file.read_text() == "caller owned"
    finally:
        body_file.unlink(missing_ok=True)


@pytest.mark.parametrize("output_format", ["json", "raw"])
def test_fetch_pr_machine_formats_preserve_valid_json(
    monkeypatch, capsys, output_format
):
    payload = '{"number":7,"title":"Keep spacing"}'
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: (payload, "", 0))
    args = argparse.Namespace(pr_or_url="7", fields=None, format=output_format)

    gh.cmd_fetch_pr(args)

    assert capsys.readouterr().out == payload + "\n"


def test_fetch_pr_malformed_json_fails(monkeypatch, capsys):
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: ("not-json", "", 0))
    args = argparse.Namespace(pr_or_url="7", fields=None, format="human")

    with pytest.raises(SystemExit) as error:
        gh.cmd_fetch_pr(args)

    assert error.value.code == 1
    assert "malformed JSON" in capsys.readouterr().err


@pytest.mark.parametrize("output_format", ["json", "raw"])
def test_fetch_issue_machine_formats_preserve_valid_json(
    monkeypatch, capsys, output_format
):
    payload = '{"number":7,"url":"https://github.com/acme/widgets/issues/7"}'
    commands = []

    def fake_run(command, *args, **kwargs):
        commands.append(command)
        return payload, "", 0

    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "run", fake_run)
    args = argparse.Namespace(
        issue_num="https://github.com/acme/widgets/issues/7",
        fields=None,
        format=output_format,
    )

    gh.cmd_fetch_issue(args)

    output = capsys.readouterr()
    assert output.out == payload + "\n"
    assert commands[0][3] == "7"
    assert commands[0][-2:] == ["--repo", "acme/widgets"]


def test_fetch_issue_rejects_foreign_url_before_fetch(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "run", lambda *args: calls.append(args) or ("", "", 0))
    args = argparse.Namespace(
        issue_num="https://github.com/other/project/issues/7",
        fields=None,
        format="json",
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_fetch_issue(args)

    assert error.value.code == 1
    assert calls == []
    assert "foreign repository" in capsys.readouterr().err


@pytest.mark.parametrize("output_format", ["human", "json", "raw"])
def test_fetch_issue_malformed_json_fails_without_payload(
    monkeypatch, capsys, output_format
):
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: ("not-json", "", 0))
    args = argparse.Namespace(issue_num="7", fields=None, format=output_format)

    with pytest.raises(SystemExit) as error:
        gh.cmd_fetch_issue(args)

    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "malformed JSON" in output.err


def test_create_issue_json_is_deterministic_and_preserves_body(monkeypatch, capsys):
    body_file = TMP / "gh-safety-create-issue.md"
    body_file.write_text("issue body")
    upstream = {
        "title": "Issue title",
        "html_url": "https://github.com/acme/widgets/issues/7",
        "number": 7,
    }
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    payloads = []

    def fake_run(command, *args, **kwargs):
        payloads.append(json.loads(Path(command[command.index("--input") + 1]).read_text()))
        return json.dumps(upstream), "", 0

    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    monkeypatch.setattr(gh, "run", fake_run)
    args = argparse.Namespace(
        title="Issue title",
        body_file=str(body_file),
        label=None,
        assignee=None,
        unclaimed=False,
        format="json",
    )
    try:
        gh.cmd_create_issue(args)

        assert json.loads(capsys.readouterr().out) == {
            "number": 7,
            "url": "https://github.com/acme/widgets/issues/7",
        }
        assert body_file.read_text() == "issue body"
        assert payloads == [
            {"assignees": ["creator"], "body": "issue body", "title": "Issue title"}
        ]
    finally:
        body_file.unlink(missing_ok=True)


def test_specs_ensure_reuses_one_open_matching_issue(monkeypatch, capsys):
    existing = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": "# Specs: Ship widgets\n\nPrimary Issue: #20\n",
        "state": "open",
        "labels": [{"name": "spec"}],
    }

    def fake_api(method, endpoint, data=None, **kwargs):
        if endpoint.startswith("labels"):
            assert data is None
            return '[{"name":"spec"}]', "", 0
        if endpoint.startswith("issues?"):
            assert data is None
            return json.dumps([existing]), "", 0
        if endpoint == "issues/20":
            if method == "GET":
                return json.dumps({"state": "open", "labels": [], "body": "Specs: #77\n"}), "", 0
            pytest.fail("linked primary issue must not be rewritten")
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "api", fake_api)

    gh.cmd_specs_ensure(
        argparse.Namespace(primary="20", title="Ship widgets", format="json")
    )

    assert json.loads(capsys.readouterr().out) == {
        "action": "reused",
        "number": 77,
        "url": "https://github.com/acme/widgets/issues/77",
    }


@pytest.mark.parametrize(
    ("primary_issue", "message"),
    [
        ({"state": "closed", "labels": []}, "must be open"),
        (
            {
                "state": "open",
                "labels": [],
                "pull_request": {"url": "https://api.github.com/pulls/20"},
            },
            "must not be a pull request",
        ),
        ({"state": "open", "labels": [{"name": "roadmap"}]}, "must not be roadmap"),
        ({"state": "open", "labels": [{"name": "spec"}]}, "must not be spec"),
    ],
)
def test_specs_ensure_rejects_invalid_primary_before_any_write(
    monkeypatch, capsys, primary_issue, message
):
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/20":
            return json.dumps(primary_issue), "", 0
        pytest.fail(f"invalid primary must stop before {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_ensure(
            argparse.Namespace(primary="20", title="Ship widgets", format="json")
        )

    assert error.value.code == 1
    assert calls == [("GET", "issues/20", None)]
    assert message in capsys.readouterr().err


def test_specs_ensure_rejects_duplicate_matching_issues(monkeypatch, capsys):
    issue = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": "Primary Issue: #20",
        "state": "open",
        "labels": [{"name": "spec"}],
    }

    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(
        gh,
        "api",
        lambda method, endpoint, **kwargs: (
            json.dumps({"state": "open", "labels": []})
            if endpoint == "issues/20"
            else '[{"name":"spec"}]'
            if endpoint.startswith("labels")
            else json.dumps([issue, issue]),
            "",
            0,
        ),
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_ensure(
            argparse.Namespace(primary="20", title="Ship widgets", format="json")
        )

    assert error.value.code == 1
    assert "multiple" in capsys.readouterr().err


def test_specs_ensure_rejects_ambiguous_primary_markers(monkeypatch, capsys):
    issue = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": "Primary Issue: #20\nPrimary Issue: #21\n",
    }
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/20":
            return json.dumps({"state": "open", "labels": []}), "", 0
        if endpoint.startswith("labels"):
            return '[{"name":"spec"}]', "", 0
        if endpoint.startswith("issues?"):
            return json.dumps([issue]), "", 0
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_ensure(
            argparse.Namespace(primary="20", title="Ship widgets", format="json")
        )

    assert error.value.code == 1
    assert not any(method == "POST" for method, _, _ in calls)
    assert "ambiguous primary issue markers" in capsys.readouterr().err


def test_specs_ensure_rejects_conflicting_primary_reference_before_creation(
    monkeypatch, capsys
):
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/20":
            return (
                json.dumps(
                    {
                        "state": "open",
                        "labels": [],
                        "body": "# Ship widgets\n\nSpecs: #76\n",
                    }
                ),
                "",
                0,
            )
        if endpoint.startswith("labels"):
            return "[]", "", 0
        if method == "POST" and endpoint == "labels":
            return "{}", "", 0
        if method == "GET" and endpoint.startswith("issues?"):
            return "[]", "", 0
        if method == "POST" and endpoint == "issues":
            return (
                json.dumps(
                    {
                        "number": 77,
                        "html_url": "https://github.com/acme/widgets/issues/77",
                    }
                ),
                "",
                0,
            )
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_ensure(
            argparse.Namespace(primary="20", title="Ship widgets", format="json")
        )

    assert error.value.code == 1
    assert not any(
        method == "POST" and endpoint in {"labels", "issues"}
        for method, endpoint, _ in calls
    )
    assert "already links a different or duplicate Specs issue" in capsys.readouterr().err


def test_specs_ensure_rejects_foreign_primary_issue_url(monkeypatch, capsys):
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(
        gh,
        "api",
        lambda *args, **kwargs: pytest.fail("foreign issue URL must not reach the API"),
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_ensure(
            argparse.Namespace(
                primary="https://github.com/other/widgets/issues/20",
                title="Ship widgets",
                format="json",
            )
        )

    assert error.value.code == 1
    assert "foreign repository" in capsys.readouterr().err


def test_specs_ensure_ignores_matching_pull_requests(monkeypatch, capsys):
    pull_request = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/pull/77",
        "title": "Spec: Ship widgets",
        "body": "Primary Issue: #20",
        "pull_request": {"url": "https://api.github.com/repos/acme/widgets/pulls/77"},
    }
    created = {
        "number": 78,
        "html_url": "https://github.com/acme/widgets/issues/78",
    }

    monkeypatch.setattr(
        gh,
        "api",
        lambda method, endpoint, data=None, **kwargs: (
            (json.dumps({"state": "open", "labels": []}), "", 0)
            if method == "GET" and endpoint == "issues/20"
            else ('[{"name":"spec"}]', "", 0)
            if endpoint.startswith("labels")
            else (json.dumps([pull_request]), "", 0)
            if method == "GET" and endpoint.startswith("issues?")
            else (json.dumps(created), "", 0)
            if method == "POST"
            else (json.dumps({"body": "Specs: #78\n"}), "", 0)
        ),
    )

    gh.cmd_specs_ensure(
        argparse.Namespace(primary="20", title="Ship widgets", format="json")
    )

    assert json.loads(capsys.readouterr().out)["number"] == 78


def test_specs_ensure_links_primary_issue_once(monkeypatch, capsys):
    calls = []
    specs_issue = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": "Primary Issue: #20",
    }
    primary_issue = {"state": "open", "labels": [], "body": "# Ship widgets\n"}

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if endpoint.startswith("labels"):
            return '[{"name":"spec"}]', "", 0
        if endpoint.startswith("issues?"):
            return json.dumps([specs_issue]), "", 0
        if method == "GET" and endpoint == "issues/20":
            return json.dumps(primary_issue), "", 0
        if method == "PATCH" and endpoint == "issues/20":
            primary_issue["body"] = data["body"]
            return "{}", "", 0
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)
    args = argparse.Namespace(primary="20", title="Ship widgets", format="json")

    gh.cmd_specs_ensure(args)
    capsys.readouterr()
    gh.cmd_specs_ensure(args)

    assert primary_issue["body"] == "# Ship widgets\n\nSpecs: #77\n"
    assert [call[:2] for call in calls].count(("PATCH", "issues/20")) == 1


@pytest.mark.parametrize(
    "body",
    [
        "Previous Primary Issue: #20\n",
    ],
)
def test_specs_ensure_does_not_reuse_noncanonical_primary_marker(monkeypatch, capsys, body):
    existing = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": body,
    }
    created = {
        "number": 78,
        "html_url": "https://github.com/acme/widgets/issues/78",
    }
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if endpoint.startswith("labels"):
            return '[{"name":"spec"}]', "", 0
        if endpoint.startswith("issues?"):
            return json.dumps([existing]), "", 0
        if method == "POST" and endpoint == "issues":
            return json.dumps(created), "", 0
        if method == "GET" and endpoint == "issues/20":
            return json.dumps({"state": "open", "labels": [], "body": "# Ship widgets\n"}), "", 0
        if method == "PATCH" and endpoint == "issues/20":
            return "{}", "", 0
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)

    gh.cmd_specs_ensure(
        argparse.Namespace(primary="20", title="Ship widgets", format="json")
    )

    assert json.loads(capsys.readouterr().out)["action"] == "created"
    assert any(method == "POST" and endpoint == "issues" for method, endpoint, _ in calls)


def test_specs_ensure_reuses_match_from_paginated_lookup(monkeypatch, capsys):
    later_page_match = {
        "number": 77,
        "html_url": "https://github.com/acme/widgets/issues/77",
        "title": "Spec: Ship widgets",
        "body": "Primary Issue: #20\n",
    }
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if endpoint.startswith("labels"):
            return '[{"name":"spec"}]', "", 0
        if endpoint.startswith("issues?"):
            assert kwargs.get("paginate") is True
            return json.dumps([later_page_match]), "", 0
        if method == "GET" and endpoint == "issues/20":
            return json.dumps({"state": "open", "labels": [], "body": "Specs: #77\n"}), "", 0
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)

    gh.cmd_specs_ensure(
        argparse.Namespace(primary="20", title="Ship widgets", format="json")
    )

    assert json.loads(capsys.readouterr().out)["action"] == "reused"
    assert not any(method == "POST" for method, _, _ in calls)


def test_specs_publish_appends_complete_revision_and_updates_index(
    monkeypatch, capsys, tmp_path
):
    paths = {}
    for name in ("spec", "design", "plan", "task"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"{name} content", encoding="utf-8")
        paths[name] = str(path)
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/77":
            return json.dumps({"state": "open", "labels": [{"name": "spec"}], "body": "Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n"}), "", 0
        if method == "GET" and endpoint.startswith("issues/77/comments"):
            return "[]", "", 0
        if method == "POST":
            number = len([call for call in calls if call[0] == "POST"])
            return json.dumps({"html_url": f"https://github.com/acme/widgets/issues/77#issuecomment-{number}"}), "", 0
        return "{}", "", 0

    monkeypatch.setattr(gh, "check_file", lambda path: True)
    monkeypatch.setattr(gh, "api", fake_api)

    gh.cmd_specs_publish(
        argparse.Namespace(number=77, revision=1, primary=20, format="json", **paths)
    )

    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == 1
    assert set(result["documents"]) == set(paths)
    assert calls[-1][0:2] == ("PATCH", "issues/77")
    assert "Current Revision**: 1" in calls[-1][2]["body"]


def test_specs_index_renders_explicit_current_document_links():
    base = "https://github.com/acme/widgets/issues/77"
    documents = {
        "spec": f"{base}#issuecomment-1",
        "design": f"{base}#issuecomment-2",
        "plan": f"{base}#issuecomment-3",
        "task": f"{base}#issuecomment-4",
    }

    index = gh._specs_index(
        "Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n",
        1,
        documents,
    )

    for label, name in (
        ("Spec", "spec"),
        ("Design", "design"),
        ("Implementation Plan", "plan"),
        ("Tasks", "task"),
    ):
        assert f"- **{label}**: [{label}]({documents[name]})" in index

    next_documents = documents | {"spec": f"{base}#issuecomment-5"}
    current = gh._specs_index(index, 2, next_documents).split("## Revision History")[0]

    assert next_documents["spec"] in current
    assert documents["spec"] not in current


@pytest.mark.parametrize(
    ("specs_issue", "message"),
    [
        (
            {
                "state": "open",
                "labels": [],
                "body": "Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n",
            },
            "must be labelled spec",
        ),
        (
            {
                "state": "open",
                "labels": [{"name": "spec"}],
                "pull_request": {"url": "https://api.github.com/pulls/77"},
                "body": "Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n",
            },
            "must not be a pull request",
        ),
    ],
)
def test_specs_publish_rejects_non_spec_issue_before_documents_or_writes(
    monkeypatch, capsys, tmp_path, specs_issue, message
):
    calls = []
    paths = {name: str(tmp_path / f"{name}.md") for name in ("spec", "design", "plan", "task")}

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/77":
            return json.dumps(specs_issue), "", 0
        pytest.fail(f"invalid Specs issue must stop before {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(
        gh, "check_file", lambda path: pytest.fail("invalid Specs issue must not read documents")
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_publish(
            argparse.Namespace(number=77, revision=1, primary=20, format="json", **paths)
        )

    assert error.value.code == 1
    assert calls == [("GET", "issues/77", None)]
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("current,revision", [("1", 1), ("2", 1), ("2", 2)])
def test_specs_publish_rejects_duplicate_or_stale_revision_before_posting(
    monkeypatch, tmp_path, current, revision
):
    paths = {}
    for name in ("spec", "design", "plan", "task"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"{name} content", encoding="utf-8")
        paths[name] = str(path)
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        return (
            json.dumps(
                {
                    "state": "open",
                    "labels": [{"name": "spec"}],
                    "body": (
                        "Primary Issue: #20\n\n"
                        f"**Current Revision**: {current}\n\n## Revision History\n"
                    ),
                }
            ),
            "",
            0,
        )

    monkeypatch.setattr(gh, "check_file", lambda path: True)
    monkeypatch.setattr(gh, "api", fake_api)

    with pytest.raises(SystemExit):
        gh.cmd_specs_publish(
            argparse.Namespace(number=77, revision=revision, primary=20, format="json", **paths)
        )

    assert [call for call in calls if call[0] == "POST"] == []


@pytest.mark.parametrize(
    "body",
    [
        "Previous Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n",
        "Primary Issue: #20\nPrimary Issue: #20\n\n**Current Revision**: none\n\n"
        "## Revision History\n",
    ],
)
def test_specs_publish_rejects_noncanonical_primary_marker(
    monkeypatch, capsys, tmp_path, body
):
    paths = {
        name: str(tmp_path / f"{name}.md")
        for name in ("spec", "design", "plan", "task")
    }
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/77":
            return json.dumps({"state": "open", "labels": [{"name": "spec"}], "body": body}), "", 0
        pytest.fail(f"unexpected API call: {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "check_file", lambda path: True)

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_publish(
            argparse.Namespace(number=77, revision=1, primary=20, format="json", **paths)
        )

    assert error.value.code == 1
    assert [call for call in calls if call[0] == "POST"] == []
    assert "does not identify the primary issue" in capsys.readouterr().err


def test_specs_publish_rejects_duplicate_current_revision_before_documents(
    monkeypatch, capsys, tmp_path
):
    paths = {
        name: str(tmp_path / f"{name}.md")
        for name in ("spec", "design", "plan", "task")
    }
    calls = []
    body = (
        "Primary Issue: #20\n\n**Current Revision**: none\n\n"
        "**Current Revision**: none\n\n## Revision History\n"
    )

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/77":
            return json.dumps({"state": "open", "labels": [{"name": "spec"}], "body": body}), "", 0
        pytest.fail(f"duplicate revision markers must stop before {method} {endpoint}")

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(
        gh,
        "check_file",
        lambda path: pytest.fail("duplicate revision markers must not read documents"),
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_specs_publish(
            argparse.Namespace(number=77, revision=1, primary=20, format="json", **paths)
        )

    assert error.value.code == 1
    assert calls == [("GET", "issues/77", None)]
    assert "exactly one valid current-revision marker" in capsys.readouterr().err


def test_specs_publish_accepts_the_next_sequential_revision(monkeypatch, capsys, tmp_path):
    paths = {}
    for name in ("spec", "design", "plan", "task"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"{name} content", encoding="utf-8")
        paths[name] = str(path)
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET" and endpoint == "issues/77":
            return (
                json.dumps(
                    {
                        "state": "open",
                        "labels": [{"name": "spec"}],
                        "body": (
                            "Primary Issue: #20\n\n**Current Revision**: 1\n\n"
                            "## Revision History\n"
                        ),
                    }
                ),
                "",
                0,
            )
        if method == "GET":
            return "[]", "", 0
        if method == "POST":
            return (
                json.dumps(
                    {
                        "html_url": (
                            "https://github.com/acme/widgets/issues/77"
                            f"#issuecomment-{len(calls)}"
                        )
                    }
                ),
                "",
                0,
            )
        return "{}", "", 0

    monkeypatch.setattr(gh, "check_file", lambda path: True)
    monkeypatch.setattr(gh, "api", fake_api)

    gh.cmd_specs_publish(
        argparse.Namespace(number=77, revision=2, primary=20, format="json", **paths)
    )

    assert json.loads(capsys.readouterr().out)["revision"] == 2
    assert "Current Revision**: 2" in calls[-1][2]["body"]


@pytest.mark.parametrize("failure_after", [0, 1, 2, 3, "index"])
def test_specs_publish_resumes_partial_revision_without_duplicate_comments(
    monkeypatch, capsys, tmp_path, failure_after
):
    paths = {}
    for name in ("spec", "design", "plan", "task"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"{name} content", encoding="utf-8")
        paths[name] = str(path)
    comments = []
    post_attempts = 0
    fail_once = True
    index = "Primary Issue: #20\n\n**Current Revision**: none\n\n## Revision History\n"

    def fake_api(method, endpoint, data=None, **kwargs):
        nonlocal fail_once, index, post_attempts
        if method == "GET" and endpoint == "issues/77":
            return json.dumps({"state": "open", "labels": [{"name": "spec"}], "body": index}), "", 0
        if method == "GET" and endpoint.startswith("issues/77/comments"):
            return json.dumps(comments), "", 0
        if method == "POST":
            if fail_once and failure_after != "index" and post_attempts == failure_after:
                fail_once = False
                return "", "transient failure", 1
            post_attempts += 1
            comments.append(
                {
                    "body": data["body"],
                    "html_url": (
                        "https://github.com/acme/widgets/issues/77"
                        f"#issuecomment-{len(comments) + 1}"
                    ),
                }
            )
            return json.dumps(comments[-1]), "", 0
        if fail_once and failure_after == "index":
            fail_once = False
            return "", "transient failure", 1
        index = data["body"]
        return "{}", "", 0

    monkeypatch.setattr(gh, "check_file", lambda path: True)
    monkeypatch.setattr(gh, "api", fake_api)
    args = argparse.Namespace(number=77, revision=1, primary=20, format="json", **paths)

    with pytest.raises(SystemExit):
        gh.cmd_specs_publish(args)
    capsys.readouterr()
    gh.cmd_specs_publish(args)

    assert len(comments) == 4
    assert len({comment["body"] for comment in comments}) == 4
    assert "Current Revision**: 1" in index


def test_create_issue_unclaimed_omits_assignees(monkeypatch, capsys):
    body_file = TMP / "gh-safety-create-unclaimed-issue.md"
    body_file.write_text("issue body")
    payloads = []

    def fake_run(command, *args, **kwargs):
        payloads.append(json.loads(Path(command[command.index("--input") + 1]).read_text()))
        return '{"number":7,"html_url":"https://github.com/acme/widgets/issues/7"}', "", 0

    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(
        gh,
        "authenticated_login",
        lambda: pytest.fail("unclaimed issue must not resolve an actor"),
    )
    monkeypatch.setattr(gh, "run", fake_run)
    args = argparse.Namespace(
        title="Issue title",
        body_file=str(body_file),
        label=None,
        assignee=None,
        unclaimed=True,
        format="json",
    )
    try:
        gh.cmd_create_issue(args)

        assert json.loads(capsys.readouterr().out)["number"] == 7
        assert payloads == [{"body": "issue body", "title": "Issue title"}]
    finally:
        body_file.unlink(missing_ok=True)


@pytest.mark.parametrize("response", ["not-json", "{}"])
def test_create_issue_json_failure_emits_no_payload(
    monkeypatch, capsys, response
):
    body_file = TMP / "gh-safety-create-issue-failure.md"
    body_file.write_text("issue body")
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: (response, "", 0))
    args = argparse.Namespace(
        title="Issue title",
        body_file=str(body_file),
        label=None,
        assignee=None,
        unclaimed=False,
        format="json",
    )
    try:
        with pytest.raises(SystemExit) as error:
            gh.cmd_create_issue(args)

        output = capsys.readouterr()
        assert error.value.code == 1
        assert output.out == ""
        assert "[FAIL]" in output.err
        assert body_file.read_text() == "issue body"
    finally:
        body_file.unlink(missing_ok=True)


PR_BODY = """## Summary
Safe create.
## How to Test
Run tests.
## Review Notes
None.
## Related Issues
Refs #7
"""


def _create_pr_args(body_file, output_format="json", **overrides):
    values = {
        "title": "feat: safe create",
        "body_file": str(body_file),
        "head": "topic",
        "base": "main",
        "draft": False,
        "format": output_format,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_create_pr_json_is_deterministic_and_preserves_body(monkeypatch, capsys):
    body_file = TMP / "gh-safety-create-pr.md"
    body_file.write_text(PR_BODY)
    calls = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        if method == "GET":
            return "[]", "", 0
        return json.dumps({"number": 9, "html_url": "https://github.com/acme/widgets/pull/9"}), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    claims = []
    monkeypatch.setattr(
        gh,
        "claim_number",
        lambda number, actor=None: claims.append((number, actor)) or {},
    )
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "check_branch_on_remote", lambda branch: True)
    try:
        gh.cmd_create_pr(_create_pr_args(body_file))

        assert json.loads(capsys.readouterr().out) == {
            "action": "created",
            "base": "main",
            "head": "topic",
            "number": 9,
            "url": "https://github.com/acme/widgets/pull/9",
        }
        assert calls[-1][2]["body"] == PR_BODY
        assert calls[-1][2]["draft"] is True
        assert claims == [(9, "creator")]
        assert body_file.read_text() == PR_BODY
    finally:
        body_file.unlink(missing_ok=True)


def test_create_pr_updates_exact_existing_open_pr(monkeypatch, capsys):
    body_file = TMP / "gh-safety-update-pr.md"
    body_file.write_text(PR_BODY)
    existing = [{
        "number": 9,
        "html_url": "https://github.com/acme/widgets/pull/9",
        "title": "old",
        "body": "old",
        "base": {"ref": "develop"},
        "draft": True,
        "head": {"ref": "topic"},
    }]
    calls = []
    commands = []

    def fake_api(method, endpoint, data=None, **kwargs):
        calls.append((method, endpoint, data))
        payload = existing if endpoint.startswith("pulls?") else existing[0]
        return json.dumps(payload), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "run", lambda command, *args, **kwargs: commands.append(command) or ("", "", 0))
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    claims = []
    monkeypatch.setattr(
        gh,
        "claim_number",
        lambda number, actor=None: claims.append((number, actor)) or {},
    )
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "check_branch_on_remote", lambda branch: True)
    try:
        gh.cmd_create_pr(_create_pr_args(body_file))

        assert calls == [
            ("GET", "pulls?state=open&head=acme%3Atopic", None),
            ("GET", "pulls/9", None),
            ("PATCH", "pulls/9", {
                "title": "feat: safe create",
                "body": PR_BODY,
                "base": "main",
            }),
        ]
        assert commands == []
        assert claims == [(9, "creator")]
        assert json.loads(capsys.readouterr().out)["action"] == "updated"
    finally:
        body_file.unlink(missing_ok=True)


@pytest.mark.parametrize("response", ["not-json", "{}", "[{},{}]"])
def test_create_pr_rejects_malformed_or_nonunique_lookup(
    monkeypatch, capsys, response
):
    body_file = TMP / "gh-safety-invalid-pr-lookup.md"
    body_file.write_text(PR_BODY)
    monkeypatch.setattr(gh, "api", lambda *args, **kwargs: (response, "", 0))
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "check_branch_on_remote", lambda branch: True)
    try:
        with pytest.raises(SystemExit) as error:
            gh.cmd_create_pr(_create_pr_args(body_file))

        assert error.value.code == 1
        assert capsys.readouterr().out == ""
    finally:
        body_file.unlink(missing_ok=True)


def test_create_pr_retry_rediscovers_successful_remote_write(monkeypatch, capsys):
    body_file = TMP / "gh-safety-retry-pr.md"
    body_file.write_text(PR_BODY)
    existing = []
    posts = 0

    def fake_api(method, endpoint, data=None, **kwargs):
        nonlocal posts
        if endpoint.startswith("pulls?"):
            return json.dumps(existing), "", 0
        if method == "GET":
            return json.dumps(existing[0]), "", 0
        if method == "POST":
            posts += 1
            created = {
                "number": 9,
                "html_url": "https://github.com/acme/widgets/pull/9",
                "title": data["title"],
                "body": data["body"],
                "base": {"ref": data["base"]},
                "draft": data.get("draft", False),
                "head": {"ref": data["head"]},
            }
            existing.append(created)
            return json.dumps(created), "", 0
        return json.dumps(existing[0]), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    monkeypatch.setattr(gh, "claim_number", lambda *args, **kwargs: {})
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "check_branch_on_remote", lambda branch: True)
    try:
        gh.cmd_create_pr(_create_pr_args(body_file))
        capsys.readouterr()
        gh.cmd_create_pr(_create_pr_args(body_file))

        assert posts == 1
        assert json.loads(capsys.readouterr().out)["action"] == "unchanged"
    finally:
        body_file.unlink(missing_ok=True)


def test_create_pr_preserves_existing_ready_state(monkeypatch, capsys):
    body_file = TMP / "gh-safety-draft-pr.md"
    body_file.write_text(PR_BODY)
    existing = {
        "number": 9,
        "node_id": "PR_node",
        "html_url": "https://github.com/acme/widgets/pull/9",
        "title": "feat: safe create",
        "body": PR_BODY,
        "base": {"ref": "main"},
        "draft": False,
        "head": {"ref": "topic"},
    }
    api_calls = []
    commands = []

    def fake_api(method, endpoint, data=None, **kwargs):
        api_calls.append((method, endpoint, data))
        payload = [existing] if endpoint.startswith("pulls?") else existing
        return json.dumps(payload), "", 0

    def fake_run(command, *args, **kwargs):
        commands.append(command)
        existing["draft"] = True
        return "{}", "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "run", fake_run)
    monkeypatch.setattr(gh, "authenticated_login", lambda: "creator")
    monkeypatch.setattr(gh, "claim_number", lambda *args, **kwargs: {})
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "check_branch_on_remote", lambda branch: True)
    try:
        args = _create_pr_args(body_file, draft=True)
        gh.cmd_create_pr(args)
        assert json.loads(capsys.readouterr().out)["action"] == "unchanged"
        gh.cmd_create_pr(args)

        assert all(call[0] != "PATCH" for call in api_calls)
        assert commands == []
        assert json.loads(capsys.readouterr().out)["action"] == "unchanged"
    finally:
        body_file.unlink(missing_ok=True)


@pytest.mark.parametrize("output_format", ["json", "raw"])
def test_cmd_machine_formats_preserve_valid_json(monkeypatch, capsys, output_format):
    payload = '[{"number":7}]'
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: (payload, "", 0))

    gh.cmd_cmd(argparse.Namespace(gh_args=["pr", "list"], format=output_format))

    assert capsys.readouterr().out == payload + "\n"


def test_cmd_json_format_rejects_malformed_json(monkeypatch, capsys):
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: ("not-json", "", 0))

    with pytest.raises(SystemExit) as error:
        gh.cmd_cmd(argparse.Namespace(gh_args=["pr", "list"], format="json"))

    assert error.value.code == 1
    assert "malformed JSON" in capsys.readouterr().err


def test_plain_pr_url_fallback_supplies_complete_namespace(monkeypatch):
    received = []
    monkeypatch.setattr(gh, "cmd_fetch_pr", received.append)

    gh.cmd_fetch_url(argparse.Namespace(url="https://github.com/acme/widgets/pull/7"))

    assert vars(received[0]) == {
        "pr_or_url": "7",
        "fields": None,
        "format": "human",
    }


def test_unknown_top_level_command_is_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gh.py", "frobnicate", "thing"])

    with pytest.raises(SystemExit) as error:
        gh.main()

    output = capsys.readouterr()
    assert error.value.code == 2
    assert "gh.py cmd frobnicate thing" in output.err
    assert "raw `gh`" not in output.out + output.err


def test_main_parses_explicit_formats_for_fetch_pr_and_cmd(monkeypatch):
    received = []
    monkeypatch.setattr(gh, "cmd_fetch_pr", received.append)
    monkeypatch.setattr(sys, "argv", ["gh.py", "fetch", "pr", "7", "--format", "json"])
    gh.main()

    monkeypatch.setattr(gh, "cmd_cmd", received.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gh.py", "cmd", "--format", "raw", "api", "repos/acme/widgets"],
    )
    gh.main()

    assert received[0].format == "json"
    assert received[1].format == "raw"
    assert received[1].gh_args == ["api", "repos/acme/widgets"]


def test_main_parses_explicit_issue_formats(monkeypatch):
    received = []
    issue_url = "https://github.com/acme/widgets/issues/7"
    monkeypatch.setattr(gh, "cmd_fetch_issue", received.append)
    monkeypatch.setattr(
        sys, "argv", ["gh.py", "fetch", "issue", issue_url, "--format", "raw"]
    )
    gh.main()

    monkeypatch.setattr(gh, "cmd_create_issue", received.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gh.py", "create-issue", "Title", "body.md", "--format", "json"],
    )
    gh.main()

    assert received[0].issue_num == issue_url
    assert received[0].format == "raw"
    assert received[1].format == "json"


def test_main_parses_explicit_create_format(monkeypatch):
    received = []
    monkeypatch.setattr(gh, "cmd_create_pr", received.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gh.py", "create", "Title", "body.md", "--format", "json"],
    )

    gh.main()

    assert received[0].format == "json"


def test_authenticated_login_fails_closed_on_missing_identity(monkeypatch, capsys):
    monkeypatch.setattr(gh, "run", lambda *args, **kwargs: ("", "not logged in", 1))

    with pytest.raises(SystemExit) as error:
        gh.authenticated_login()

    assert error.value.code == 1
    assert "authenticated GitHub login" in capsys.readouterr().err


def test_claim_number_adds_actor_without_replacing_assignees(monkeypatch):
    issue = {
        "number": 7,
        "html_url": "https://github.com/acme/widgets/issues/7",
        "assignees": [{"login": "reviewer"}],
    }
    monkeypatch.setattr(
        gh, "api", lambda *args, **kwargs: (json.dumps(issue), "", 0)
    )
    added = []
    def fake_add(number, assignees):
        added.append((number, assignees))
        issue["assignees"].extend({"login": login} for login in assignees)

    monkeypatch.setattr(gh, "add_assignees", fake_add)

    result = gh.claim_number(7, "creator")

    assert added == [(7, ["creator"])]
    assert result["assignees"] == ["reviewer", "creator"]
    assert result["action"] == "claimed"


def test_claim_number_fails_when_assignment_is_not_observed(monkeypatch, capsys):
    issue = {
        "number": 7,
        "html_url": "https://github.com/acme/widgets/issues/7",
        "assignees": [{"login": "reviewer"}],
    }
    monkeypatch.setattr(
        gh, "api", lambda *args, **kwargs: (json.dumps(issue), "", 0)
    )
    monkeypatch.setattr(gh, "add_assignees", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as error:
        gh.claim_number(7, "creator")

    assert error.value.code == 1
    assert "could not be verified" in capsys.readouterr().err


def test_claim_number_is_idempotent(monkeypatch):
    issue = {
        "number": 7,
        "html_url": "https://github.com/acme/widgets/issues/7",
        "assignees": [{"login": "creator"}, {"login": "reviewer"}],
    }
    monkeypatch.setattr(
        gh, "api", lambda *args, **kwargs: (json.dumps(issue), "", 0)
    )
    monkeypatch.setattr(
        gh,
        "add_assignees",
        lambda *args, **kwargs: pytest.fail("must not rewrite assignees"),
    )

    result = gh.claim_number(7, "creator")

    assert result["action"] == "unchanged"
    assert result["assignees"] == ["creator", "reviewer"]


def test_main_routes_claim_command(monkeypatch):
    received = []
    monkeypatch.setattr(gh, "cmd_claim", received.append)
    monkeypatch.setattr(
        sys, "argv", ["gh.py", "claim", "7", "--format", "json"]
    )

    gh.main()

    assert received[0].number == 7
    assert received[0].format == "json"


@pytest.mark.parametrize(
    "failed_endpoint", ["pulls/7", "pulls/7/comments", "pulls/7/reviews"]
)
@pytest.mark.parametrize("failure", ["api", "json"])
def test_fetch_comments_fails_before_writing_when_required_fetch_fails(
    monkeypatch, capsys, failed_endpoint, failure
):
    output = TMP / "gh-safety-fetch-failure.md"
    output.unlink(missing_ok=True)

    def fake_api(method, endpoint, **kwargs):
        if endpoint == failed_endpoint:
            return ("not-json", "", 0) if failure == "json" else ("", "failed", 1)
        payload = {
            "pulls/7": {
                "head": {"ref": "topic", "sha": "head"},
                "base": {"sha": "base"},
            },
            "pulls/7/comments": [],
            "pulls/7/reviews": [],
        }[endpoint]
        return json.dumps(payload), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    args = argparse.Namespace(
        pr_or_url="7", output=str(output), all=True, urls_only=False
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_fetch_comments(args)

    assert error.value.code == 1
    assert not output.exists()
    assert "[FAIL]" in capsys.readouterr().err


def test_fetch_comments_emits_bodyless_review_inline_comment_once(monkeypatch):
    output = TMP / "gh-safety-bodyless-review.md"
    output.unlink(missing_ok=True)
    responses = {
        "pulls/7": {"head": {"ref": "topic", "sha": "head"}, "base": {"sha": "base"}},
        "pulls/7/comments": [
            {
                "id": 22,
                "pull_request_review_id": 11,
                "path": "widget.py",
                "line": 3,
                "html_url": "https://github.com/acme/widgets/pull/7#discussion_r22",
                "body": "bodyless review comment",
                "user": {"login": "reviewer"},
            }
        ],
        "pulls/7/reviews": [{"id": 11, "body": ""}],
    }
    monkeypatch.setattr(
        gh,
        "api",
        lambda method, endpoint, **kwargs: (json.dumps(responses[endpoint]), "", 0),
    )
    args = argparse.Namespace(
        pr_or_url="7", output=str(output), all=True, urls_only=False
    )
    try:
        gh.cmd_fetch_comments(args)

        assert output.read_text().count("bodyless review comment") == 1
    finally:
        output.unlink(missing_ok=True)


@pytest.mark.parametrize("failed_fetch", ["threads", "review_minimization"])
@pytest.mark.parametrize("failure", ["api", "json"])
def test_fetch_active_comments_fails_before_writing_when_graphql_fetch_fails(
    monkeypatch, capsys, failed_fetch, failure
):
    output = TMP / "gh-safety-graphql-failure.md"
    output.unlink(missing_ok=True)
    responses = {
        "pulls/7": {"head": {"ref": "topic"}, "base": {}},
        "pulls/7/comments": [],
        "pulls/7/reviews": [{"id": 11, "node_id": "PRR_node", "body": "review"}],
    }
    monkeypatch.setattr(
        gh,
        "api",
        lambda method, endpoint, **kwargs: (json.dumps(responses[endpoint]), "", 0),
    )
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    thread_payload = {
        "data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}
    }
    calls = 0

    def fake_run(command, *args, **kwargs):
        nonlocal calls
        calls += 1
        stage = "threads" if calls == 1 else "review_minimization"
        if stage == failed_fetch:
            return ("not-json", "", 0) if failure == "json" else ("", "failed", 1)
        payload = (
            thread_payload
            if stage == "threads"
            else {"data": {"_0": {"isMinimized": False}}}
        )
        return json.dumps(payload), "", 0

    monkeypatch.setattr(gh, "run", fake_run)
    args = argparse.Namespace(
        pr_or_url="7", output=str(output), all=False, urls_only=False
    )

    with pytest.raises(SystemExit) as error:
        gh.cmd_fetch_comments(args)

    assert error.value.code == 1
    assert not output.exists()
    assert "[FAIL]" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["direct", "parent", "child"])
def test_batch_close_exits_partial_when_any_operation_fails(monkeypatch, failure):
    batch_file = TMP / f"gh-safety-batch-{failure}.json"
    if failure == "direct":
        items = [{"url": "https://github.com/acme/widgets/pull/7#discussion_r22"}]
    else:
        items = [
            {
                "url": "https://github.com/acme/widgets/pull/7#pullrequestreview-11",
                "classifier": "OUTDATED",
            }
        ]
    batch_file.write_text(json.dumps(items))
    comments = [{"id": 22, "pull_request_review_id": 11}]
    reviews = [{"id": 11, "node_id": "PRR_node"}]

    def fake_api(method, endpoint, **kwargs):
        payload = comments if endpoint.endswith("/comments") else reviews
        return json.dumps(payload), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(gh, "fetch_thread_map", lambda owner, pr: {})
    monkeypatch.setattr(
        gh,
        "resolve_single_comment",
        lambda pr, comment_id, thread_map: failure not in {"direct", "child"},
    )
    monkeypatch.setattr(
        gh, "minimize_single_review", lambda node_id, classifier: failure != "parent"
    )
    try:
        with pytest.raises(SystemExit) as error:
            gh.cmd_batch_close(
                argparse.Namespace(pr_or_url="7", json_file=str(batch_file))
            )

        assert error.value.code == gh.EXIT_PARTIAL
    finally:
        batch_file.unlink(missing_ok=True)


def test_fetch_discussion_url_fetches_matching_review_comment(monkeypatch, capsys):
    calls = []

    def fake_api(method, endpoint, **kwargs):
        calls.append(endpoint)
        return json.dumps({"id": 22, "body": "specific comment"}), "", 0

    monkeypatch.setattr(gh, "api", fake_api)
    monkeypatch.setattr(
        gh, "run", lambda *args, **kwargs: pytest.fail("unexpected subprocess call")
    )

    gh.cmd_fetch_url(
        argparse.Namespace(url="https://github.com/acme/widgets/pull/7#discussion_r22")
    )

    assert calls == ["pulls/comments/22"]
    assert json.loads(capsys.readouterr().out)["id"] == 22


def test_fetch_thread_map_paginates_threads_and_nested_comments(monkeypatch):
    calls = []

    def fake_run(command, *args, **kwargs):
        query = command[-1].removeprefix("query=")
        calls.append(query)
        nested = "comments(first: 100, after:" in query
        if nested:
            nodes = [{"fullDatabaseId": 1000 + i, "isMinimized": False} for i in range(21, 121)]
            payload = {"data": {"node": {"comments": {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        else:
            page_two = 'reviewThreads(first: 100, after: "threads-1")' in query
            start = 101 if page_two else 1
            count = 5 if page_two else 100
            threads = []
            for i in range(start, start + count):
                comments = [{"fullDatabaseId": i, "isMinimized": False}]
                page_info = {"hasNextPage": False, "endCursor": None}
                if i == 1:
                    comments = [{"fullDatabaseId": n, "isMinimized": False} for n in range(1, 21)]
                    page_info = {"hasNextPage": True, "endCursor": "comments-1"}
                threads.append({"id": f"T{i}", "isResolved": False, "comments": {"nodes": comments, "pageInfo": page_info}})
            payload = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads, "pageInfo": {"hasNextPage": not page_two, "endCursor": "threads-1" if not page_two else None}}}}}}
        return json.dumps(payload), "", 0

    monkeypatch.setattr(gh, "run", fake_run)
    result = gh.fetch_thread_map("acme/widgets", "7")

    assert len(result) == 205
    assert result["1120"]["thread_id"] == "T1"
    assert len(calls) == 3


def test_rest_api_pagination_flattens_every_page_without_unsupported_flags(monkeypatch):
    commands = []
    monkeypatch.setattr(gh, "get_owner_repo", lambda: "acme/widgets")
    monkeypatch.setattr(
        gh,
        "run",
        lambda command: commands.append(command)
        or ('[{"id":1}]\n[{"id":2}]', "", 0),
    )

    output, _, rc = gh.api("GET", "pulls/7/comments", paginate=True)

    assert rc == 0
    assert json.loads(output) == [{"id": 1}, {"id": 2}]
    assert "--paginate" in commands[0]
    assert "--slurp" not in commands[0]


def test_review_minimization_batches_beyond_graphql_alias_limit(monkeypatch):
    calls = []

    def fake_run(command):
        calls.append(command)
        query = command[-1]
        count = query.count(": node(")
        return json.dumps({"data": {f"_{i}": {"isMinimized": False} for i in range(count)}}), "", 0

    monkeypatch.setattr(gh, "run", fake_run)
    reviews = [{"node_id": f"R{i}"} for i in range(101)]

    assert len(gh.fetch_review_minimization(reviews)) == 101
    assert len(calls) == 3
