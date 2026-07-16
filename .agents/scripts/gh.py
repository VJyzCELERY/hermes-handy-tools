#!/usr/bin/env python3
"""GitHub PR and review helper script.

Usage:
    # PR / Review operations
    uv run python .agents/scripts/gh.py fetch pr <pr-or-url>          # Get PR details
    uv run python .agents/scripts/gh.py fetch comments <pr-or-url>    # Get PR comments/reviews
    uv run python .agents/scripts/gh.py fetch comments <pr-or-url> [--all]  # Get active inline comments/reviews (use --all for everything)
    uv run python .agents/scripts/gh.py fetch url <full-url>          # Fetch specific by URL
    uv run python .agents/scripts/gh.py fetch repo                    # Get repo info (owner, language, etc.)
    uv run python .agents/scripts/gh.py fetch prs                     # List PRs (filters: --head, --state, --base, --limit)
    uv run python .agents/scripts/gh.py post review <pr> <body.md> [comments.json]
    uv run python .agents/scripts/gh.py post comment <pr-or-issue> <body.md>
    uv run python .agents/scripts/gh.py post inline <pr> <body.md> --path <file> --line <N>
    uv run python .agents/scripts/gh.py post reply <pr> <comment-id> <body.md>
    uv run python .agents/scripts/gh.py resolve <pr> <comment-id>
    uv run python .agents/scripts/gh.py minimize <pr> <comment-id> [--classifier RESOLVED|OUTDATED|DUPLICATE]
    uv run python .agents/scripts/gh.py unminimize <pr> <comment-id>
    uv run python .agents/scripts/gh.py batch close <pr> <batch.json>
    uv run python .agents/scripts/gh.py interact minimize <url> [--classifier OUTDATED]
    uv run python .agents/scripts/gh.py interact resolve <url>
    uv run python .agents/scripts/gh.py interact unminimize <url>
    uv run python .agents/scripts/gh.py interact reply <url> <body.md>
    uv run python .agents/scripts/gh.py update body <pr> <body.md>
    uv run python .agents/scripts/gh.py update title <pr> <title>
    uv run python .agents/scripts/gh.py update issue body <issue> <body.md>
    uv run python .agents/scripts/gh.py update issue title <issue> <title>
    uv run python .agents/scripts/gh.py create <title> <body.md> --head <branch> [--base <branch>]
    
    # Issue operations
    uv run python .agents/scripts/gh.py fetch issue <num>             # Get issue details
    uv run python .agents/scripts/gh.py fetch issues                  # List issues (filters: --state, --label, --assignee, --limit)
    uv run python .agents/scripts/gh.py create-issue <title> <body.md> [--label <labels>] [--assignee <users>]
    
    # Utilities
    uv run python .agents/scripts/gh.py cmd <gh-args>              # Run any gh command with auto-formatted output
    uv run python .agents/scripts/gh.py fields [pr|prs|repo]       # List available JSON fields for --json
    
    If a command is not available, use `cmd` to run it raw:
    uv run python .agents/scripts/gh.py cmd issue list

<EOF_DESC>
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cli_common import EXIT_PARTIAL
import repo_guard


TMP_DIR = repo_guard.repo_root() / "tmp"


def run(cmd, input_data=None, check=True):
    try:
        r = subprocess.run(cmd, text=True, capture_output=True, input=input_data, check=check)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip(), e.returncode
    except FileNotFoundError as e:
        return "", f"Command not found: {e.filename}", 1


def get_owner_repo():
    out, _, rc = run(["gh", "repo", "view", "--json", "owner,name", "--jq", r'"\(.owner.login)/\(.name)"'])
    if rc != 0:
        sys.exit("Cannot detect owner/repo. Are you authenticated with `gh`?")
    return out


def parse_pr_input(arg: str) -> str:
    """Parse PR number from a number, URL, or partial URL."""
    arg = arg.strip()
    # Full GitHub PR URL
    m = re.search(r"github\.com/[^/]+/[^/]+/pull/(\d+)", arg)
    if m:
        return m.group(1)
    # Plain number
    if arg.isdigit():
        return arg
    sys.exit(f"Could not parse PR number from: {arg}")


def parse_issue_input(arg: str) -> tuple[str, str | None]:
    """Parse an issue number and optional repository from an issue reference."""
    arg = arg.strip()
    match = re.fullmatch(
        r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)/?", arg
    )
    if match:
        return match.group(3), f"{match.group(1)}/{match.group(2)}"
    if arg.isdigit():
        return arg, None
    sys.exit(f"Could not parse issue number from: {arg}")


def parse_url_input(url: str) -> dict:
    """Parse a full GitHub URL to extract type and ID.
    
    Examples:
        https://github.com/owner/repo/pull/11#issue-4399302650
        https://github.com/owner/repo/pull/4#pullrequestreview-4216020278
    """
    result = {"pr": None, "type": None, "id": None, "url": url}
    m = re.search(r"github\.com/[^/]+/[^/]+/pull/(\d+)", url)
    if m:
        result["pr"] = m.group(1)
    # Check for fragment identifiers
    frag = urllib.parse.urlparse(url).fragment
    if frag:
        fm = re.match(r"(issue|pullrequestreview)-(\d+)|discussion_r(\d+)", frag)
        if fm:
            result["type"] = fm.group(1) or "discussion_r"
            result["id"] = fm.group(2) or fm.group(3)
    return result


def api(method: str, endpoint: str, data: dict | None = None, input_file: str | None = None, paginate: bool = False) -> tuple[str, str, int]:
    OWNER_REPO = get_owner_repo()
    url = f"repos/{OWNER_REPO}/{endpoint.lstrip('/')}"
    cmd = ["gh", "api", url, "--method", method]
    
    if paginate:
        cmd.append("--paginate")
    
    if input_file:
        cmd.extend(["--input", input_file])
    elif data:
        for k, v in data.items():
            cmd.extend(["-f", f"{k}={v}"])
    
    out, err, rc = run(cmd)
    if paginate and rc == 0:
        try:
            decoder = json.JSONDecoder()
            pages = []
            position = 0
            while position < len(out):
                position = len(out) - len(out[position:].lstrip())
                if position == len(out):
                    break
                page, position = decoder.raw_decode(out, position)
                if not isinstance(page, list):
                    raise TypeError
                pages.extend(page)
            out = json.dumps(pages)
        except (json.JSONDecodeError, TypeError):
            pass
    return out, err, rc


def authenticated_login() -> str:
    """Return the active GitHub login or fail before a remote mutation."""
    out, err, rc = run(["gh", "api", "user", "--jq", ".login"])
    login = out.strip()
    if rc or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", login):
        detail = err or "empty or malformed response"
        print(
            f"[FAIL] Could not resolve authenticated GitHub login: {detail}",
            file=sys.stderr,
        )
        sys.exit(1)
    return login


def add_assignees(number: int, assignees: list[str]) -> None:
    """Add assignees to an issue or PR without replacing existing assignees."""
    data = {"assignees": assignees}
    with generated_payload("gh-assignees-", data) as payload:
        owner_repo = get_owner_repo()
        out, err, rc = run(
            [
                "gh",
                "api",
                f"repos/{owner_repo}/issues/{number}/assignees",
                "--method",
                "POST",
                "--input",
                str(payload),
            ]
        )
    if rc:
        print(f"[FAIL] Could not assign #{number}: {err or out}", file=sys.stderr)
        sys.exit(1)


def claim_number(number: int, actor: str | None = None) -> dict:
    """Idempotently assign the authenticated actor to an issue or PR."""
    actor = actor or authenticated_login()

    def current() -> tuple[str, list[str]]:
        out, err, rc = api("GET", f"issues/{number}")
        if rc:
            print(f"[FAIL] Could not fetch #{number} for claim: {err}", file=sys.stderr)
            sys.exit(1)
        try:
            item = json.loads(out)
            url = item["html_url"]
            assignees = [entry["login"] for entry in item["assignees"]]
            if not isinstance(url, str) or not url or not all(
                isinstance(login, str) and login for login in assignees
            ):
                raise TypeError
        except (json.JSONDecodeError, KeyError, TypeError):
            print("[FAIL] GitHub returned malformed assignee JSON", file=sys.stderr)
            sys.exit(1)
        return url, assignees

    url, assignees = current()
    action = "unchanged"
    if actor not in assignees:
        add_assignees(number, [actor])
        url, assignees = current()
        if actor not in assignees:
            print(f"[FAIL] Assignment of #{number} could not be verified", file=sys.stderr)
            sys.exit(1)
        action = "claimed"
    return {
        "action": action,
        "number": number,
        "url": url,
        "actor": actor,
        "assignees": assignees,
    }


def cmd_claim(args):
    """Claim an issue or PR for the authenticated GitHub actor."""
    result = claim_number(args.number)
    if args.format == "json":
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"[OK] #{args.number} {result['action']} by {result['actor']}")


def clean_temp(path: str | Path):
    """Delete regular files owned by the repository temp directory."""
    p = Path(path)
    try:
        p.resolve().relative_to(TMP_DIR.resolve())
    except ValueError:
        return
    if p.is_file():
        p.unlink()


@contextmanager
def generated_payload(prefix: str, data: dict):
    """Create a collision-safe JSON payload and always remove it."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=TMP_DIR,
            prefix=prefix,
            suffix=".json",
            delete=False,
        ) as payload_file:
            path = Path(payload_file.name)
            json.dump(data, payload_file)
        yield path
    finally:
        if path is not None:
            clean_temp(path)


def check_file(path: str) -> bool:
    """Validate path is a regular, nonempty repository file."""
    p = repo_guard.assert_inside_repo(path)
    if not p.is_file():
        print(f"[FAIL] Not a regular file: {path}", file=sys.stderr)
        return False
    if p.stat().st_size == 0:
        print(f"[FAIL] File is empty: {path}", file=sys.stderr)
        return False
    return True


REQUIRED_PR_SECTIONS = ["## Summary", "## How to Test", "## Review Notes", "## Related Issues"]
TEMPLATE_PLACEHOLDER_RE = re.compile(
    r'\[(?:Describe|Item|Map to|What|Additional|File|List|Fill|Explain|Add|Document|Review|Example|Update|Note|Specify|Reason|Expected).*?\]',
    re.IGNORECASE,
)


def validate_pr_body(body: str) -> list[str]:
    """Validate a PR body against the project template.

    Returns a list of error messages (empty list means valid).
    """
    errors: list[str] = []

    if not body.strip():
        errors.append("PR body is empty.")
        return errors

    for section in REQUIRED_PR_SECTIONS:
        if section not in body:
            errors.append(f"Missing required section: {section}")

    placeholders = TEMPLATE_PLACEHOLDER_RE.findall(body)
    if placeholders:
        for ph in placeholders[:5]:
            errors.append(f"Unfilled placeholder found: {ph}")

    return errors


def cmd_fetch_prs(args):
    """List PRs with optional filters."""
    cmd = ["gh", "pr", "list", "--json",
           "number,title,state,headRefName,baseRefName,author,createdAt,updatedAt,mergeable,isDraft"]
    if args.head:
        cmd.extend(["--head", args.head])
    if args.state:
        cmd.extend(["--state", args.state])
    if args.base:
        cmd.extend(["--base", args.base])
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])

    out, err, rc = run(cmd)
    if rc != 0:
        print(f"[FAIL] Could not list PRs: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        prs = json.loads(out)
        if not prs:
            print("No PRs found matching the given criteria.")
            return
        print(f"PRs matching: {len(prs)} result(s)")
        print()
        for pr in prs:
            draft = " [DRAFT]" if pr.get("isDraft") else ""
            state_tag = pr["state"].upper()
            print(f"  #{pr['number']} ({state_tag}{draft}) — {pr['title']}")
            print(f"       {pr['headRefName']} → {pr['baseRefName']}  |  by {pr['author']['login']}")
            print(f"       Created: {pr['createdAt']}")
    except json.JSONDecodeError:
        print(out)


def cmd_fetch_repo(args):
    """Fetch and display repo information."""
    owner_repo = get_owner_repo()
    fields = ["name", "owner", "description", "url", "defaultBranchRef", "primaryLanguage",
              "isPrivate", "createdAt", "updatedAt", "forkCount", "hasIssuesEnabled",
              "hasWikiEnabled"]
    out, err, rc = run(["gh", "repo", "view", owner_repo, "--json", ",".join(fields)])
    if rc != 0:
        print(f"[FAIL] Could not fetch repo info: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(out)
        print(f"Repository: {data['owner']['login']}/{data['name']}")
        print(f"URL: {data.get('url', 'N/A')}")
        print(f"Description: {data.get('description', '') or '(none)'}")
        print(f"Visibility: {'Private' if data.get('isPrivate') else 'Public'}")
        print(f"Default Branch: {data.get('defaultBranchRef', {}).get('name', 'N/A')}")
        print(f"Language: {data.get('primaryLanguage', {}).get('name', 'N/A')}")
        print(f"Created: {data.get('createdAt', 'N/A')}")
        print(f"Updated: {data.get('updatedAt', 'N/A')}")
        print(f"Forks: {data.get('forkCount', 0)}")
        print(f"Issues: {'Enabled' if data.get('hasIssuesEnabled') else 'Disabled'}")
    except json.JSONDecodeError:
        print(out)


# ─── Fetch Commands ─────────────────────────────────────────────

def cmd_fetch_pr(args):
    pr = parse_pr_input(args.pr_or_url)
    # Use curated default fields — only useful info, no API URLs or nested bloat
    fields = args.fields or "number,title,state,headRefName,baseRefName,author,body,createdAt,updatedAt,mergedAt,closedAt,mergeable,isDraft,additions,deletions,changedFiles,labels,reviews,headRefOid"
    out, err, rc = run(["gh", "pr", "view", pr, "--json", fields])
    if rc != 0:
        print(f"[FAIL] Could not fetch PR #{pr}: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(out)
        if args.format in ("json", "raw"):
            print(out)
            return
        if args.fields:
            print(json_to_md(data))
            return
        
        # Get head SHA; for base SHA use API since baseRefOid isn't available in gh pr view
        head_sha = data.get("headRefOid", "")
        base_sha = ""
        if head_sha:
            owner_repo = get_owner_repo()
            if owner_repo:
                base_sha, _, _ = run(["gh", "api", f"repos/{owner_repo}/pulls/{pr}", "--jq", ".base.sha"], None, False)
        
        # HEADER section
        print(f"#{data['number']} — {data['title']}")
        print("---")
        print(f"State: {data['state'].upper()}")
        if data.get('isDraft'):
            print("Draft: Yes")
        print(f"Head: {data.get('headRefName', '?')}")
        print(f"Base: {data.get('baseRefName', '?')}")
        if base_sha and head_sha:
            print(f"Commit Range: {base_sha}...{head_sha}")
        elif head_sha:
            print(f"Head SHA: {head_sha}")
        print(f"Author: {data.get('author', {}).get('login', '?')}")
        print(f"Created: {data.get('createdAt', '?')}")
        print(f"Updated: {data.get('updatedAt', '?')}")
        if data.get('mergedAt'):
            print(f"Merged: {data['mergedAt']}")
        if data.get('closedAt'):
            print(f"Closed: {data['closedAt']}")
        print(f"Changes: +{data.get('additions', 0)} / -{data.get('deletions', 0)} ({data.get('changedFiles', 0)} files)")
        labels = data.get('labels', [])
        if labels:
            print(f"Labels: {', '.join(label.get('name', '') for label in labels)}")
        
        # Title section
        print("---")
        print(f"Title : {data['title']}")
        
        # Body section
        body = data.get('body', '')
        print("---")
        print("Body :")
        if body:
            print(f"{body}")
        else:
            print("(no body)")
        print("---")
        
        print(f"\n[INFO] Use --json to specify custom fields: gh.py fetch pr {pr} --json number,title,state")
    except json.JSONDecodeError:
        print(f"[FAIL] GitHub returned malformed JSON for PR #{pr}", file=sys.stderr)
        sys.exit(1)


def cmd_fetch_comments(args):
    pr = parse_pr_input(args.pr_or_url)

    fetched = {}
    for endpoint, expected_type in (
        (f"pulls/{pr}", dict),
        (f"pulls/{pr}/comments", list),
        (f"pulls/{pr}/reviews", list),
    ):
        out, err, rc = api("GET", endpoint, paginate=endpoint != f"pulls/{pr}")
        if rc != 0:
            print(f"[FAIL] Could not fetch {endpoint}: {err}", file=sys.stderr)
            sys.exit(1)
        try:
            fetched[endpoint] = json.loads(out)
        except json.JSONDecodeError:
            print(f"[FAIL] GitHub returned malformed JSON for {endpoint}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(fetched[endpoint], expected_type):
            print(f"[FAIL] GitHub returned unexpected JSON for {endpoint}", file=sys.stderr)
            sys.exit(1)

    pr_info = fetched[f"pulls/{pr}"]
    branch = pr_info.get("head", {}).get("ref", f"PR-{pr}")
    base_sha = pr_info.get("base", {}).get("sha", "")
    head_sha = pr_info.get("head", {}).get("sha", "")
    safe_branch = branch.replace("/", "_")
    ts = int(time.time())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    out_dir = repo_guard.assert_inside_repo(Path("reviews") / "remote")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = repo_guard.assert_inside_repo(
        args.output or out_dir / f"REVIEW_{safe_branch}_fetched_{ts}.md"
    )
    
    all_comments_raw = fetched[f"pulls/{pr}/comments"]
    
    # Filter out minimized/resolved comments by default, unless --all is given
    include_minimized = getattr(args, "all", False)
    if include_minimized:
        all_comments = all_comments_raw
    else:
        # Use GraphQL to get minimized/resolved state (REST API doesn't expose these)
        owner_repo = get_owner_repo()
        thread_map = fetch_thread_map(owner_repo, pr)
        all_comments = []
        for c in all_comments_raw:
            cid = str(c.get("id", ""))
            info = thread_map.get(cid)
            # Skip if comment is minimized or its thread is resolved
            if info and (info["is_minimized"] or info["is_resolved"]):
                continue
            all_comments.append(c)
    
    all_reviews = fetched[f"pulls/{pr}/reviews"]
    
    # Separate reviews that have a body (meaningful review) vs empty ones
    meaningful_reviews = [r for r in all_reviews if r.get("body", "").strip()]

    # Filter out minimized reviews (REST API doesn't reflect GraphQL minimization)
    if not include_minimized and meaningful_reviews:
        # Batch query GraphQL to check which reviews are minimized
        minimized = fetch_review_minimization(meaningful_reviews)
        meaningful_reviews = [
            review
            for review in meaningful_reviews
            if not minimized.get(review["node_id"], False)
        ]
    
    # --urls-only: output JSON lines of filtered review + comment URLs and exit
    urls_only = getattr(args, "urls_only", False)
    if urls_only:
        for r in meaningful_reviews:
            r_url = r.get("html_url", "")
            if r_url:
                print(json.dumps({"url": r_url}))
        for c in all_comments:
            c_url = c.get("html_url", "")
            if c_url:
                print(json.dumps({"url": c_url}))
        return

    # Group inline comments by pull_request_review_id
    comments_by_review: dict[int, list[dict]] = {}
    orphan_comments: list[dict] = []
    for c in all_comments:
        rid = c.get("pull_request_review_id")
        if rid:
            comments_by_review.setdefault(rid, []).append(c)
        else:
            orphan_comments.append(c)

    # Build the report — group reviews with their inline comments
    sections = []
    for r in meaningful_reviews:
        rid = r.get("id")
        author = r.get("user", {}).get("login", "?")
        state = r.get("state", "?")
        body = r.get("body", "")
        review_url = r.get("html_url", "?")
        submitted_at = r.get("submitted_at", "")
        
        section = f"[{state}] by {author} — {submitted_at}\nURL: {review_url}\n\n{body}"
        
        # Append inline comments that belong to this review
        inline = comments_by_review.pop(rid, [])
        for c in inline:
            loc = f"{c.get('path','?')}:{c.get('line','?')}"
            c_url = c.get("html_url", "?")
            c_body = c.get("body", "")
            section += f"\n\n---\n\n### Inline — {loc}\nURL: {c_url}\n\n{c_body}"
        
        sections.append(section)
    
    # Orphan comments (no parent review)
    for c in orphan_comments + sum(comments_by_review.values(), []):
        loc = f"{c.get('path','?')}:{c.get('line','?')}"
        c_url = c.get("html_url", "?")
        c_author = c.get("user", {}).get("login", "?")
        c_body = c.get("body", "")
        section = f"[COMMENT] by {c_author}\nURL: {c_url}\n\n### Inline — {loc}\nURL: {c_url}\n\n{c_body}"
        sections.append(section)
    
    # Write the report
    separator = "\n\n---\n\n"
    report = f"# Fetched Reviews: PR #{pr}\n**Fetched**: {now}\n**Branch**: {branch}\n"
    if base_sha and head_sha:
        report += f"**Commit Range**: {base_sha}...{head_sha}\n"
    report += "---\n\n"
    report += separator.join(sections) if sections else "No reviews found on this PR."
    
    output_path.write_text(report, encoding="utf-8")
    label = f"{len(all_comments)} active" if not include_minimized else f"{len(all_comments)} total"
    print(f"[OK] Fetched {len(meaningful_reviews)} review(s) with {label} inline comment(s) → {output_path}")
    
    # Print to stdout
    if base_sha and head_sha:
        print(f"Commit Range: {base_sha}...{head_sha}")
    print(f"\n=== Reviews ({len(meaningful_reviews)}) ===")
    for r in meaningful_reviews:
        author = r.get("user", {}).get("login", "?")
        state = r.get("state", "?")
        body = r.get("body", "")
        review_url = r.get("html_url", "?")
        submitted_at = r.get("submitted_at", "")
        print(f"  [{state}] by {author} — {submitted_at}")
        print(f"  URL: {review_url}")
        for line in body.split("\n"):
            print(f"    {line}")
    
    if all_comments:
        label = "active" if not include_minimized else "total"
        print(f"\n=== Inline Comments ({len(all_comments)} {label}) ===")
        for c in all_comments:
            loc = f"{c.get('path','?')}:{c.get('line','?')}"
            c_author = c.get("user", {}).get("login", "?")
            c_url = c.get("html_url", "?")
            c_body = c.get("body", "")
            print(f"  {loc} — {c_author}")
            print(f"  URL: {c_url}")
            for line in c_body.split("\n"):
                print(f"    {line}")


def cmd_fetch_review_state(args):
    """Emit authoritative repository, PR, actor, and feedback authorization state."""
    pr = parse_pr_input(args.pr_or_url)
    owner_repo = get_owner_repo()
    actor_out, actor_err, actor_rc = run(["gh", "api", "user", "--jq", ".login"])
    pr_out, pr_err, pr_rc = api("GET", f"pulls/{pr}")
    comments_out, comments_err, comments_rc = api(
        "GET", f"pulls/{pr}/comments", paginate=True
    )
    reviews_out, reviews_err, reviews_rc = api(
        "GET", f"pulls/{pr}/reviews", paginate=True
    )
    if actor_rc or pr_rc or comments_rc or reviews_rc:
        error = actor_err or pr_err or comments_err or reviews_err
        print(f"[FAIL] Could not inspect review state: {error}", file=sys.stderr)
        sys.exit(1)
    try:
        pr_data = json.loads(pr_out)
        comments = json.loads(comments_out)
        reviews = json.loads(reviews_out)
        if not isinstance(pr_data, dict) or not isinstance(comments, list) or not isinstance(reviews, list):
            raise TypeError
    except (json.JSONDecodeError, TypeError):
        print("[FAIL] GitHub returned malformed review inspection JSON", file=sys.stderr)
        sys.exit(1)

    thread_map = fetch_thread_map(owner_repo, pr)
    minimized_reviews = fetch_review_minimization(reviews)
    by_id = {comment.get("id"): comment for comment in comments}

    def root_id(comment):
        current = comment
        seen = set()
        while current.get("in_reply_to_id") in by_id and current["in_reply_to_id"] not in seen:
            seen.add(current["in_reply_to_id"])
            current = by_id[current["in_reply_to_id"]]
        return current.get("id")

    chains = {}
    for comment in comments:
        chains.setdefault(root_id(comment), []).append(comment)
    items = []
    for comment in comments:
        info = thread_map.get(str(comment.get("id")), {})
        if comment.get("in_reply_to_id"):
            continue
        chain = chains.get(comment.get("id"), [comment])
        items.append({
            "url": comment.get("html_url"),
            "author": comment.get("user", {}).get("login"),
            "author_type": comment.get("user", {}).get("type"),
            "active_human": not info.get("is_resolved", False)
            and not info.get("is_minimized", False)
            and any(
                entry.get("user", {}).get("type") == "User"
                and entry.get("user", {}).get("login") != actor_out
                for entry in chain
            ),
            "bodies": [entry.get("body", "") for entry in chain],
            "active": not info.get("is_resolved", False)
            and not info.get("is_minimized", False),
        })
    for review in reviews:
        if not review.get("body", "").strip():
            continue
        items.append({
            "url": review.get("html_url"),
            "author": review.get("user", {}).get("login"),
            "author_type": review.get("user", {}).get("type"),
            "active_human": not minimized_reviews.get(review.get("node_id"), False)
            and review.get("user", {}).get("type") == "User"
            and review.get("user", {}).get("login") != actor_out,
            "bodies": [review.get("body", "")],
            "active": not minimized_reviews.get(review.get("node_id"), False),
        })
    print(json.dumps({
        "repository": f"https://github.com/{owner_repo}",
        "pull_request": pr_data.get("html_url"),
        "head": pr_data.get("head", {}).get("sha"),
        "actor": actor_out,
        "items": items,
    }, sort_keys=True))


def fetch_review_minimization(reviews: list[dict]) -> dict[str, bool]:
    """Fetch minimization state for every review in bounded GraphQL batches."""
    result = {}
    with_nodes = [review for review in reviews if review.get("node_id")]
    for start in range(0, len(with_nodes), 50):
        batch = with_nodes[start : start + 50]
        nodes = " ".join(
            f'_{i}: node(id: "{review["node_id"]}") {{ ... on PullRequestReview {{ isMinimized }} }}'
            for i, review in enumerate(batch)
        )
        out, err, rc = run(["gh", "api", "graphql", "-f", f"query=query {{ {nodes} }}"])
        if rc:
            print(f"[FAIL] Could not fetch review minimization state: {err}", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(out)["data"]
            for i, review in enumerate(batch):
                result[review["node_id"]] = data[f"_{i}"]["isMinimized"]
        except (KeyError, TypeError, json.JSONDecodeError):
            print("[FAIL] GitHub returned malformed review state JSON", file=sys.stderr)
            sys.exit(1)
    return result


# ─── Post Commands ─────────────────────────────────────────────

def cmd_post_review(args):
    pr = parse_pr_input(args.pr_or_url)
    body_file = args.body_file
    comments_file = args.comments_file
    event = args.event or "COMMENT"
    
    if not check_file(body_file):
        sys.exit(1)
    with open(body_file) as f:
        body = f.read()
    
    rc = 1
    err = ""
    
    # Build and send the review payload
    # Inline comments require --input with a combined JSON payload
    if comments_file and check_file(comments_file):
        with open(comments_file) as cf:
            comments = json.load(cf)
        payload = {
            "body": body,
            "event": event,
            "comments": comments
        }
        with generated_payload("gh-review-payload-", payload) as tf:
            OWNER_REPO = get_owner_repo()
            cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/reviews",
                   "--method", "POST", "--input", str(tf)]
            out, err, rc = run(cmd)
    else:
        data = {"body": body, "event": event}
        out, err, rc = api("POST", f"pulls/{pr}/reviews", data)
    
    # Graceful fallback: if post failed due to author restrictions (e.g.
    # PR author cannot APPROVE or REQUEST_CHANGES their own PR), retry as COMMENT.
    if rc != 0 and event != "COMMENT":
        print(f"[WARN] Review post with event '{event}' failed: {err[:120]}", file=sys.stderr)
        print(f"[WARN] Retrying as 'COMMENT' event (author cannot {event} own PR).", file=sys.stderr)
        if comments_file and check_file(comments_file):
            with open(comments_file) as cf:
                comments = json.load(cf)
            payload = {
                "body": body,
                "event": "COMMENT",
                "comments": comments
            }
            with generated_payload("gh-review-payload-", payload) as tf:
                OWNER_REPO = get_owner_repo()
                cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/reviews",
                       "--method", "POST", "--input", str(tf)]
                out, err, rc = run(cmd)
        else:
            data = {"body": body, "event": "COMMENT"}
            out, err, rc = api("POST", f"pulls/{pr}/reviews", data)
    
    if rc != 0:
        print(f"[FAIL] Review post failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    # Parse response to extract review URL and ID
    review_url = ""
    review_id = ""
    if out:
        try:
            resp = json.loads(out)
            review_url = resp.get("html_url", "")
            review_id = resp.get("id", "")
        except json.JSONDecodeError:
            pass
    
    # Fetch inline comments for this review (API doesn't return them in the create response)
    comment_entries = []
    if review_id:
        cout, _, _ = api("GET", f"pulls/{pr}/comments", paginate=True)
        if cout:
            try:
                for c in json.loads(cout):
                    if c.get("pull_request_review_id") == review_id:
                        entry = {
                            "url": c.get("html_url", ""),
                            "path": c.get("path", "?"),
                            "line": c.get("line", "?"),
                            "body": c.get("body", ""),
                        }
                        comment_entries.append(entry)
            except json.JSONDecodeError:
                pass
    
    print(f"[OK] Review posted to PR #{pr}")
    print("")
    print(f"**PR Review URL**: {review_url}")
    print("")
    for e in comment_entries:
        loc = f"{e['path']}:{e['line']}"
        print(f"**PR Comment**: {e['url']}")
        print(f"**Location**: {loc}")
        for line in e['body'].split("\n"):
            print(f"  {line}")
        print("")


def cmd_post_comment(args):
    pr = parse_pr_input(args.pr_or_url)
    body_file = args.body_file
    
    if not check_file(body_file):
        sys.exit(1)
    
    out, err, rc = api("POST", f"issues/{pr}/comments", {"body": open(body_file).read()})
    if rc != 0:
        print(f"[FAIL] Comment post failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[OK] Comment posted to PR #{pr}")


def get_pr_head_sha(pr: str) -> str | None:
    """Get the latest commit SHA on the PR branch."""
    out, _, rc = run(["gh", "pr", "view", pr, "--json", "headRefOid", "--jq", ".headRefOid"])
    return out if rc == 0 and out else None


def cmd_post_inline_comment(args):
    """Post a single inline comment on a specific file/line of a PR."""
    pr = parse_pr_input(args.pr_or_url)
    body_file = args.body_file
    path = args.path
    line = args.line
    
    if not check_file(body_file):
        sys.exit(1)
    
    commit_id = get_pr_head_sha(pr)
    if not commit_id:
        print("[FAIL] Could not determine PR head commit SHA", file=sys.stderr)
        sys.exit(1)
    
    data = {
        "body": open(body_file).read(),
        "commit_id": commit_id,
        "path": path,
        "line": line,
        "side": args.side or "RIGHT"
    }
    if args.start_line:
        data["start_line"] = args.start_line
        data["start_side"] = args.start_side or "RIGHT"
    
    out, err, rc = api("POST", f"pulls/{pr}/comments", data)
    if rc != 0:
        print(f"[FAIL] Inline comment failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    comment_id = ""
    try:
        comment_id = f" (#{json.loads(out).get('id', '')})"
    except json.JSONDecodeError:
        pass
    print(f"[OK] Inline comment posted to PR #{pr} at {path}:{line}{comment_id}")


def cmd_reply_comment(args):
    """Reply to an existing review thread."""
    pr = parse_pr_input(args.pr_or_url)
    comment_id = args.comment_id
    body_file = args.body_file
    
    if not check_file(body_file):
        sys.exit(1)
    
    # Use JSON temp file to send in_reply_to as a proper number (the API rejects string IDs)
    data = {
        "body": open(body_file).read(),
        "in_reply_to": int(comment_id)
    }
    with generated_payload("gh-reply-", data) as tf:
        OWNER_REPO = get_owner_repo()
        cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/comments",
               "--method", "POST", "--input", str(tf)]
        out, err, rc = run(cmd)
    
    if rc != 0:
        print(f"[FAIL] Reply failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[OK] Reply posted to thread #{comment_id} on PR #{pr}")


def cmd_minimize_comment(args):
    """Minimize (hide) a PR comment or review body with a reason classifier.
    
    Accepts either a numeric comment/review ID or a full GitHub URL."""
    pr = parse_pr_input(args.pr_or_url)
    input_id = args.comment_id
    classifier = args.classifier
    
    # Try parsing as URL first
    parsed = parse_comment_id_from_url(input_id)
    if parsed:
        cid, ctype = parsed
        if ctype == "pullrequestreview":
            # Review body — find its node_id via REST API
            out, _, _ = api("GET", f"pulls/{pr}/reviews", paginate=True)
            node_id = None
            if out:
                try:
                    for rv in json.loads(out):
                        if str(rv.get("id")) == cid:
                            node_id = rv.get("node_id")
                            break
                except json.JSONDecodeError:
                    pass
            if not node_id:
                print(f"[FAIL] Review #{cid} not found on PR #{pr}", file=sys.stderr)
                sys.exit(1)
            mutation = f"""
            mutation {{
              minimizeComment(input: {{subjectId: "{node_id}", classifier: {classifier}}}) {{
                minimizedComment {{ __typename }}
              }}
            }}
            """
            cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
            out2, err2, rc2 = run(cmd)
            if rc2 != 0:
                print(f"[FAIL] Minimize review #{cid} failed: {err2}", file=sys.stderr)
                sys.exit(1)
            print(f"[OK] Review #{cid} minimized as {classifier}")
            return
        else:
            discussion_id = cid
    
    # Fallback: treat input as a numeric comment ID
    if not parsed:
        discussion_id = input_id
    
    # Minimize an inline comment — fetch to get node_id
    out, err, rc = api("GET", f"pulls/{pr}/comments", paginate=True)
    if rc != 0:
        print(f"[FAIL] Could not fetch comments: {err}", file=sys.stderr)
        sys.exit(1)
    
    try:
        comments = json.loads(out)
        target = None
        for c in comments:
            if str(c.get("id")) == discussion_id:
                target = c
                break
        if not target:
            print(f"[FAIL] Comment #{discussion_id} not found on PR #{pr}", file=sys.stderr)
            sys.exit(1)
        node_id = target.get("node_id")
        if not node_id:
            print(f"[FAIL] Comment #{discussion_id} has no node_id", file=sys.stderr)
            sys.exit(1)
        mutation = f"""
        mutation {{
          minimizeComment(input: {{subjectId: "{node_id}", classifier: {classifier}}}) {{
            minimizedComment {{ __typename }}
          }}
        }}
        """
        cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
        out2, err2, rc2 = run(cmd)
        if rc2 != 0:
            print(f"[FAIL] Minimize failed: {err2}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Comment #{discussion_id} minimized as {classifier}")
    except json.JSONDecodeError:
        print(f"[FAIL] Could not parse comments: {out}", file=sys.stderr)
        sys.exit(1)


def cmd_unminimize_comment(args):
    """Unminimize (restore) a previously minimized PR comment."""
    pr = parse_pr_input(args.pr_or_url)
    comment_id = args.comment_id

    out, err, rc = api("GET", f"pulls/{pr}/comments", paginate=True)
    if rc != 0:
        print(f"[FAIL] Could not fetch comments: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        comments = json.loads(out)
        target = None
        for c in comments:
            if str(c.get("id")) == comment_id:
                target = c
                break
        if not target:
            print(f"[FAIL] Comment #{comment_id} not found on PR #{pr}", file=sys.stderr)
            sys.exit(1)

        node_id = target.get("node_id")
        if not node_id:
            print(f"[FAIL] Comment #{comment_id} has no node_id", file=sys.stderr)
            sys.exit(1)

        mutation = f"""
        mutation {{
          unminimizeComment(input: {{subjectId: "{node_id}"}}) {{
            unminimizedComment {{ __typename }}
          }}
        }}
        """
        cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
        out2, err2, rc2 = run(cmd)
        if rc2 != 0:
            print(f"[FAIL] Unminimize failed: {err2}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Comment #{comment_id} restored")
    except json.JSONDecodeError:
        print(f"[FAIL] Could not parse comments: {out}", file=sys.stderr)
        sys.exit(1)


def minimize_single_comment(pr: str, comment_id: str, classifier: str, comments_cache: list[dict]) -> bool:
    """Minimize a single comment using cached comments for node_id lookup. Returns True on success."""
    target = None
    for c in comments_cache:
        if str(c.get("id")) == comment_id:
            target = c
            break
    if not target:
        print(f"[WARN] Comment #{comment_id} not found, skipping", file=sys.stderr)
        return False

    node_id = target.get("node_id")
    if not node_id:
        print(f"[WARN] Comment #{comment_id} has no node_id, skipping", file=sys.stderr)
        return False

    mutation = f"""
    mutation {{
      minimizeComment(input: {{subjectId: "{node_id}", classifier: {classifier}}}) {{
        minimizedComment {{ id }}
      }}
    }}
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
    out2, err2, rc2 = run(cmd)
    if rc2 != 0:
        print(f"[WARN] Minimize #{comment_id} as {classifier} failed: {err2}", file=sys.stderr)
        return False
    print(f"[OK] Comment #{comment_id} minimized as {classifier}")
    return True


def minimize_single_review(node_id: str, classifier: str) -> bool:
    """Minimize a pull request review body by its GraphQL node_id. Returns True on success."""
    mutation = f"""
    mutation {{
      minimizeComment(input: {{subjectId: "{node_id}", classifier: {classifier}}}) {{
        minimizedComment {{ __typename }}
      }}
    }}
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
    out2, err2, rc2 = run(cmd)
    if rc2 != 0:
        print(f"[WARN] Minimize review {node_id[:20]}... failed: {err2}", file=sys.stderr)
        return False
    print(f"[OK] Review {node_id[:20]}... minimized as {classifier}")
    return True
def parse_comment_id_from_url(url: str) -> tuple[str, str] | None:
    """Extract comment_id and type from a GitHub URL.
    
    Returns (comment_id, type) where type is 'discussion_r' or 'pullrequestreview'.
    """
    m = re.search(r'#(discussion_r|pullrequestreview)-?(\d+)', url)
    if m:
        return m.group(2), m.group(1)
    return None


def fetch_thread_map(owner_repo: str, pr: str) -> dict:
    """Fetch all review threads for a PR and return a dict mapping comment_id -> thread info.

    Returns: {comment_id_str: {"thread_id": str, "is_resolved": bool, "is_minimized": bool}}
    """
    owner, repo = owner_repo.split("/", 1)
    thread_map = {}
    thread_cursor = None
    while True:
        after = f', after: "{thread_cursor}"' if thread_cursor else ""
        query = f"""
        query {{
      repository(owner: "{owner}", name: "{repo}") {{
        pullRequest(number: {pr}) {{
          reviewThreads(first: 100{after}) {{
            nodes {{
              id
              isResolved
              comments(first: 100) {{
                nodes {{
                  id
                  fullDatabaseId
                  isMinimized
                }}
                pageInfo {{ hasNextPage endCursor }}
              }}
            }}
            pageInfo {{
              hasNextPage
              endCursor
            }}
          }}
        }}
      }}
    }}
    """
        out, err, rc = run(["gh", "api", "graphql", "-f", f"query={query}"])
        if rc != 0 or not out:
            print(f"[FAIL] Could not fetch review threads: {err}", file=sys.stderr)
            sys.exit(1)
        try:
            connection = json.loads(out)["data"]["repository"]["pullRequest"]["reviewThreads"]
            page_info = connection["pageInfo"]
        except (KeyError, TypeError, json.JSONDecodeError):
            print("[FAIL] GitHub returned malformed review thread JSON", file=sys.stderr)
            sys.exit(1)
        for thread in connection["nodes"]:
            comments = thread["comments"]
            _add_thread_comments(thread_map, thread, comments["nodes"])
            comment_cursor = comments["pageInfo"].get("endCursor")
            while comments["pageInfo"].get("hasNextPage"):
                comments = _fetch_thread_comments(thread["id"], comment_cursor)
                _add_thread_comments(thread_map, thread, comments["nodes"])
                comment_cursor = comments["pageInfo"].get("endCursor")
        if not page_info.get("hasNextPage"):
            return thread_map
        thread_cursor = page_info.get("endCursor")


def _fetch_thread_comments(thread_id: str, cursor: str) -> dict:
    query = f'''query {{ node(id: "{thread_id}") {{ ... on PullRequestReviewThread {{ comments(first: 100, after: "{cursor}") {{ nodes {{ fullDatabaseId isMinimized }} pageInfo {{ hasNextPage endCursor }} }} }} }} }}'''
    out, err, rc = run(["gh", "api", "graphql", "-f", f"query={query}"])
    if rc:
        print(f"[FAIL] Could not fetch nested review comments: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(out)["data"]["node"]["comments"]
    except (KeyError, TypeError, json.JSONDecodeError):
        print("[FAIL] GitHub returned malformed nested comment JSON", file=sys.stderr)
        sys.exit(1)


def _add_thread_comments(thread_map: dict, thread: dict, comments: list[dict]) -> None:
    for c in comments:
            cid = str(c.get("fullDatabaseId", ""))
            if cid:
                thread_map[cid] = {
                    "thread_id": thread["id"],
                    "is_resolved": thread["isResolved"],
                    "is_minimized": c.get("isMinimized", False),
                }


def resolve_single_comment(pr: str, comment_id: str, thread_map: dict | None = None) -> bool:
    """Resolve a single inline comment thread via GraphQL. Returns True on success."""
    owner_repo = get_owner_repo()
    if thread_map is None:
        thread_map = fetch_thread_map(owner_repo, pr)

    info = thread_map.get(comment_id)
    if not info:
        print(f"[WARN] Comment #{comment_id} thread not found, skipping", file=sys.stderr)
        return False

    if info["is_resolved"]:
        print(f"[OK] Comment #{comment_id} already resolved")
        return True

    tid = info["thread_id"]
    mutation = f"""
    mutation {{
      resolveReviewThread(input: {{threadId: "{tid}"}}) {{
        thread {{ id }}
      }}
    }}
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
    out2, err2, rc2 = run(cmd)
    if rc2 != 0:
        print(f"[WARN] Resolve #{comment_id} failed: {err2}", file=sys.stderr)
        return False
    print(f"[OK] Comment #{comment_id} resolved")
    return True


def cmd_batch_close(args):
    """Close multiple PR comments from a JSON file — resolves inline comments, minimizes non-inline ones.

    JSON format entries (one of):
      {"url": "https://.../...#discussion_r<id>"}         — resolves the inline thread
      {"url": "https://.../...#pullrequestreview<id>", "classifier": "OUTDATED"}  — minimizes as classifier

    The command auto-detects the type from the URL fragment and performs the correct action.
    Performs validation before any API calls.
    """
    pr = parse_pr_input(args.pr_or_url)
    json_file = args.json_file

    if not check_file(json_file):
        sys.exit(1)

    with open(json_file) as f:
        try:
            items = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[FAIL] Invalid JSON in {json_file}: {e}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(items, list):
        print("[FAIL] JSON must be an array of {url} or {url, classifier} objects", file=sys.stderr)
        sys.exit(1)

    # Validate all entries before any API calls
    errors = []
    parsed_entries = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"  [{i}] not an object: {item}")
            continue
        url = item.get("url", "")
        if not url:
            errors.append(f"  [{i}] missing 'url'")
            continue
        parsed = parse_comment_id_from_url(url)
        if not parsed:
            errors.append(f"  [{i}] URL does not contain #discussion_r or #pullrequestreview: {url}")
            continue
        cid, ctype = parsed
        if ctype == "pullrequestreview":
            cls = item.get("classifier", "OUTDATED")
            if cls not in ("RESOLVED", "OUTDATED", "DUPLICATE"):
                errors.append(f"  [{i}] invalid 'classifier': {cls}")
                continue
            parsed_entries.append(("minimize", cid, cls, url))
        else:
            parsed_entries.append(("resolve", cid, None, url))

    if errors:
        print("[FAIL] Batch close JSON validation errors:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    if not parsed_entries:
        print("[WARN] No valid entries to process", file=sys.stderr)
        return

    # Fetch all comments (needed for finding review child comments)
    out, _, _ = api("GET", f"pulls/{pr}/comments", paginate=True)
    comments_cache = []
    if out:
        try:
            comments_cache = json.loads(out)
        except json.JSONDecodeError:
            pass

    # Fetch all reviews (needed for mapping review db id -> node_id for minimize)
    reviews_out, _, _ = api("GET", f"pulls/{pr}/reviews", paginate=True)
    reviews_by_id: dict[int, dict] = {}
    if reviews_out:
        try:
            for rv in json.loads(reviews_out):
                reviews_by_id[rv["id"]] = rv
        except (json.JSONDecodeError, KeyError):
            pass

    # Fetch thread map for resolve operations
    owner_repo = get_owner_repo()
    thread_map = fetch_thread_map(owner_repo, pr)

    ok = 0
    fail = 0
    for action, cid, cls, url in parsed_entries:
        if action == "resolve":
            if resolve_single_comment(pr, cid, thread_map):
                ok += 1
            else:
                fail += 1
        elif action == "minimize":
            review_id_num = int(cid)
            # Step 1: resolve all child inline comments
            child_comments = [c for c in comments_cache if c.get("pull_request_review_id") == review_id_num]
            child_ok = 0
            child_fail = 0
            for cc in child_comments:
                if resolve_single_comment(pr, str(cc["id"]), thread_map):
                    child_ok += 1
                else:
                    child_fail += 1
            fail += child_fail
            if child_comments:
                print(f"[OK] Review #{review_id_num}: resolved {child_ok}/{len(child_comments)} inline comment(s)")

            # Step 2: minimize the parent review body
            review_node_id = reviews_by_id.get(review_id_num, {}).get("node_id")
            if review_node_id:
                if minimize_single_review(review_node_id, cls):
                    ok += 1
                else:
                    fail += 1
            else:
                print(f"[WARN] Review #{review_id_num} has no node_id, cannot minimize parent", file=sys.stderr)
                fail += 1

    print(f"[OK] Batch close done: {ok} succeeded, {fail} failed")
    if fail:
        sys.exit(EXIT_PARTIAL)


def cmd_resolve_comment(args):
    """Resolve a review thread via GraphQL. Accepts a comment ID or full URL."""
    pr = parse_pr_input(args.pr_or_url)
    input_id = args.comment_id
    
    # Try parsing as URL first
    parsed = parse_comment_id_from_url(input_id)
    comment_id = parsed[0] if parsed else input_id
    
    # Use the thread_map-based resolver (same as batch close)
    owner_repo = get_owner_repo()
    thread_map = fetch_thread_map(owner_repo, pr)
    if resolve_single_comment(pr, comment_id, thread_map):
        print(f"[OK] Comment #{comment_id} resolved")
    else:
        sys.exit(1)


def cmd_update_body(args):
    pr = parse_pr_input(args.pr_or_url)
    body_file = args.body_file
    
    if not check_file(body_file):
        sys.exit(1)
    
    out, err, rc = api("PATCH", f"pulls/{pr}", {"body": open(body_file).read()})
    if rc != 0:
        print(f"[FAIL] Body update failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[OK] PR #{pr} body updated")


def cmd_update_title(args):
    pr = parse_pr_input(args.pr_or_url)
    title = args.title
    out, err, rc = api("PATCH", f"pulls/{pr}", {"title": title})
    if rc != 0:
        print(f"[FAIL] Title update failed: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] PR #{pr} title updated to: {title}")


def detect_pr_base(head: str | None = None) -> str:
    if head:
        branch = head
    else:
        try:
            branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
        except Exception:
            branch = ""
    if not branch:
        return "main"
    
    # Check worktree.base-branch git config (set by create-worktree.py)
    try:
        cfg = subprocess.check_output(
            ["git", "config", "--local", "worktree.base-branch"],
            text=True, stderr=subprocess.DEVNULL).strip()
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["gh", "pr", "list", "--head", branch, "--state", "open",
             "--json", "baseRefName", "--jq", ".[0].baseRefName"],
            text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            return out
    except Exception:
        pass

    # Find the tightest parent branch (most recent common ancestor = closest to HEAD)
    best_candidate = "main"
    best_distance = 999999  # lower = closer to HEAD

    try:
        head_rev = subprocess.check_output(["git", "rev-parse", branch], text=True).strip()
        branches = subprocess.check_output(
            ["git", "branch", "--list", "--format", "%(refname:short)"],
            text=True, stderr=subprocess.DEVNULL).splitlines()
        for b in branches:
            b = b.strip().replace("* ", "")
            if b in ("main", "master", "develop", branch):
                continue
            try:
                subprocess.check_output(
                    ["git", "merge-base", "--is-ancestor", b, branch],
                    stderr=subprocess.DEVNULL)
                # b is an ancestor → it's a potential parent
                # Get the merge-base commit
                mb = subprocess.check_output(
                    ["git", "merge-base", b, branch], text=True, stderr=subprocess.DEVNULL).strip()
                if not mb:
                    continue
                # Count commits between merge-base and HEAD — smaller = tighter
                count_out = subprocess.check_output(
                    ["git", "rev-list", "--count", f"{mb}..{head_rev}"],
                    text=True, stderr=subprocess.DEVNULL).strip()
                count = int(count_out) if count_out else 999999
                # Also count commits between mb and b's HEAD — 0 means b hasn't moved
                b_head = subprocess.check_output(
                    ["git", "rev-parse", b], text=True, stderr=subprocess.DEVNULL).strip()
                b_count_out = subprocess.check_output(
                    ["git", "rev-list", "--count", f"{mb}..{b_head}"],
                    text=True, stderr=subprocess.DEVNULL).strip()
                b_count = int(b_count_out) if b_count_out else 999999

                total = count + b_count
                if total < best_distance:
                    best_distance = total
                    best_candidate = b
            except Exception:
                continue
    except Exception:
        pass

    return best_candidate if best_candidate else "main"


def check_branch_on_remote(branch: str) -> bool:
    """Check if a branch exists on the remote origin."""
    try:
        r = subprocess.run(["git", "rev-parse", f"origin/{branch}"], text=True, capture_output=True, check=False)
        return r.returncode == 0
    except Exception:
        return False


def cmd_create_pr(args):
    title = args.title
    body_file = args.body_file
    try:
        head = args.head or subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except Exception:
        head = ""
    base = args.base or detect_pr_base(head)
    
    if not head:
        print("[FAIL] Could not determine head branch. Use --head <branch>.", file=sys.stderr)
        sys.exit(1)
    if not check_file(body_file):
        sys.exit(1)
    
    # Check both branches exist on remote before creating PR — no automatic push
    if not check_branch_on_remote(head):
        print(f"[FAIL] Head branch '{head}' is not on remote. Push it first with:", file=sys.stderr)
        print(f"       git push origin {head}", file=sys.stderr)
        sys.exit(1)
    if base != head and not check_branch_on_remote(base):
        print(f"[FAIL] Base branch '{base}' is not on remote. Push it first with:", file=sys.stderr)
        print(f"       git push origin {base}", file=sys.stderr)
        sys.exit(1)
    
    # Validate PR body against template
    body = open(body_file).read()
    body_errors = validate_pr_body(body)
    if body_errors:
        print("[FAIL] PR body has template validation errors:", file=sys.stderr)
        for err in body_errors:
            print(f"       - {err}", file=sys.stderr)
        print("       Use `.agents/templates/PR-body.md` and fill in all sections.", file=sys.stderr)
        sys.exit(1)

    actor = authenticated_login()
    
    owner_repo = get_owner_repo()
    owner = owner_repo.split("/", 1)[0]
    qualified_head = urllib.parse.quote(f"{owner}:{head}", safe="")
    out, err, rc = api("GET", f"pulls?state=open&head={qualified_head}")
    if rc != 0:
        print(f"[FAIL] Could not check existing PRs: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        matches = json.loads(out)
        if not isinstance(matches, list) or len(matches) > 1:
            raise TypeError
    except (json.JSONDecodeError, TypeError):
        print("[FAIL] GitHub returned malformed or nonunique open PR JSON", file=sys.stderr)
        sys.exit(1)

    desired = {"title": title, "body": body, "base": base}
    if matches:
        existing = matches[0]
        try:
            number = existing["number"]
            url = existing["html_url"]
            detail_out, detail_err, detail_rc = api("GET", f"pulls/{number}")
            if detail_rc:
                print(
                    f"[FAIL] Could not fetch current PR state: {detail_err}",
                    file=sys.stderr,
                )
                sys.exit(1)
            detail = json.loads(detail_out)
            current = {
                "title": detail["title"],
                "body": detail["body"],
                "base": detail["base"]["ref"],
            }
            if (
                not isinstance(number, int)
                or not isinstance(url, str)
                or not url
                or not isinstance(detail["draft"], bool)
            ):
                raise TypeError
        except (json.JSONDecodeError, KeyError, TypeError):
            print("[FAIL] GitHub returned malformed open PR JSON", file=sys.stderr)
            sys.exit(1)
        changes = {key: value for key, value in desired.items() if current[key] != value}
        action = "unchanged"
        if changes:
            out, err, rc = api("PATCH", f"pulls/{number}", changes)
            action = "updated"
            if rc != 0:
                print(f"[FAIL] PR {action} failed: {err}", file=sys.stderr)
                sys.exit(1)
    else:
        out, err, rc = api(
            "POST", "pulls", {**desired, "draft": True, "head": head}
        )
        action = "created"

    if rc != 0:
        print(f"[FAIL] PR {action} failed: {err}", file=sys.stderr)
        sys.exit(1)
    if action == "created":
        try:
            response = json.loads(out)
            number = response["number"]
            url = response["html_url"]
            if not isinstance(number, int) or not isinstance(url, str) or not url:
                raise TypeError
        except (json.JSONDecodeError, KeyError, TypeError):
            print("[FAIL] GitHub returned malformed PR mutation JSON", file=sys.stderr)
            sys.exit(1)

    claim_number(number, actor)

    result = {"action": action, "number": number, "url": url, "head": head, "base": base}
    if args.format == "json":
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"[OK] PR {action}: {url} ({head} -> {base})")


# ─── URL-based handler ──────────────────────────────────────────

def _parse_interact_url(url: str) -> tuple[str, str, str]:
    """Parse a full interaction URL into (pr, comment_id, type). type is 'discussion_r' or 'pullrequestreview'."""
    m = re.search(r'pulls/(\d+)|pull/(\d+)', url)
    pr = m.group(1) or m.group(2) if m else None
    if not pr:
        print(f"[FAIL] Could not extract PR number from URL: {url}", file=sys.stderr)
        sys.exit(1)
    parsed = parse_comment_id_from_url(url)
    if not parsed:
        print(f"[FAIL] URL does not contain #discussion_r or #pullrequestreview: {url}", file=sys.stderr)
        sys.exit(1)
    return pr, parsed[0], parsed[1]


def cmd_handle_minimize(args):
    """Minimize a comment or review body by URL."""
    pr, cid, ctype = _parse_interact_url(args.url)
    classifier = args.classifier
    if ctype == "discussion_r":
        out, _, _ = api("GET", f"pulls/{pr}/comments", paginate=True)
        comments_cache = json.loads(out) if out else []
        if not minimize_single_comment(pr, cid, classifier, comments_cache):
            sys.exit(1)
    else:
        out, _, _ = api("GET", f"pulls/{pr}/reviews", paginate=True)
        node_id = None
        if out:
            for rv in json.loads(out):
                if str(rv.get("id")) == cid:
                    node_id = rv.get("node_id")
                    break
        if not node_id:
            print(f"[FAIL] Review #{cid} not found", file=sys.stderr)
            sys.exit(1)
        if not minimize_single_review(node_id, classifier):
            sys.exit(1)
    print(f"[OK] {ctype} #{cid} minimized as {classifier}")


def cmd_handle_resolve(args):
    """Resolve an inline comment thread by URL."""
    pr, cid, ctype = _parse_interact_url(args.url)
    if ctype != "discussion_r":
        print("[FAIL] Only inline comments can be resolved", file=sys.stderr)
        sys.exit(1)
    owner_repo = get_owner_repo()
    thread_map = fetch_thread_map(owner_repo, pr)
    if not resolve_single_comment(pr, cid, thread_map):
        sys.exit(1)


def cmd_handle_unminimize(args):
    """Unminimize a comment or review body by URL."""
    pr, cid, ctype = _parse_interact_url(args.url)
    if ctype == "discussion_r":
        out, _, _ = api("GET", f"pulls/{pr}/comments", paginate=True)
        if not out:
            print("[FAIL] Could not fetch comments", file=sys.stderr)
            sys.exit(1)
        comments_cache = json.loads(out)
        target = None
        for c in comments_cache:
            if str(c.get("id")) == cid:
                target = c
                break
        if not target:
            print(f"[FAIL] Comment #{cid} not found", file=sys.stderr)
            sys.exit(1)
        node_id = target.get("node_id")
    else:
        out, _, _ = api("GET", f"pulls/{pr}/reviews", paginate=True)
        if not out:
            print("[FAIL] Could not fetch reviews", file=sys.stderr)
            sys.exit(1)
        node_id = None
        for rv in json.loads(out):
            if str(rv.get("id")) == cid:
                node_id = rv.get("node_id")
                break
        if not node_id:
            print(f"[FAIL] Review #{cid} not found", file=sys.stderr)
            sys.exit(1)
    
    mutation = f"""
    mutation {{
      unminimizeComment(input: {{subjectId: "{node_id}"}}) {{
        unminimizedComment {{ __typename }}
      }}
    }}
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={mutation}"]
    out2, err2, rc2 = run(cmd)
    if rc2 != 0:
        print(f"[FAIL] Unminimize failed: {err2}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] {ctype} #{cid} unminimized")


def cmd_handle_reply(args):
    """Reply to an inline comment thread by URL."""
    pr, cid, ctype = _parse_interact_url(args.url)
    if ctype != "discussion_r":
        print("[FAIL] Cannot reply to a review body (only inline comments)", file=sys.stderr)
        sys.exit(1)
    if not check_file(args.body_file):
        sys.exit(1)
    data = {"body": open(args.body_file).read(), "in_reply_to": int(cid)}
    with generated_payload("gh-reply-", data) as tf:
        owner_repo = get_owner_repo()
        cmd = ["gh", "api", f"repos/{owner_repo}/pulls/{pr}/comments",
               "--method", "POST", "--input", str(tf)]
        out2, err2, rc2 = run(cmd)
    if rc2 != 0:
        print(f"[FAIL] Reply failed: {err2}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] Reply posted to thread #{cid} on PR #{pr}")



def cmd_fetch_url(args):
    """Fetch a specific comment or review from its full URL."""
    parsed = parse_url_input(args.url)
    if not parsed["pr"]:
        print("[FAIL] Could not parse PR number from URL", file=sys.stderr)
        sys.exit(1)
    
    if parsed["type"] == "issue":
        # Fetch a specific issue/PR comment
        out, err, rc = api("GET", f"pulls/{parsed['pr']}/comments", paginate=True)
        if rc == 0:
            try:
                for c in json.loads(out):
                    if str(c.get("id")) == parsed["id"]:
                        print(json.dumps(c, indent=2))
                        return
                print(f"[FAIL] Comment #{parsed['id']} not found", file=sys.stderr)
                sys.exit(1)
            except json.JSONDecodeError:
                print(out)
    elif parsed["type"] == "discussion_r":
        out, err, rc = api("GET", f"pulls/comments/{parsed['id']}")
        if rc != 0:
            print(f"[FAIL] Could not fetch comment #{parsed['id']}: {err}", file=sys.stderr)
            sys.exit(1)
        try:
            print(json.dumps(json.loads(out), indent=2))
        except json.JSONDecodeError:
            print("[FAIL] GitHub returned malformed JSON", file=sys.stderr)
            sys.exit(1)
    elif parsed["type"] == "pullrequestreview":
        # Fetch a specific review
        out, err, rc = api("GET", f"pulls/{parsed['pr']}/reviews", paginate=True)
        if rc == 0:
            try:
                for r in json.loads(out):
                    if str(r.get("id")) == parsed["id"]:
                        print(json.dumps(r, indent=2))
                        return
                print(f"[FAIL] Review #{parsed['id']} not found", file=sys.stderr)
                sys.exit(1)
            except json.JSONDecodeError:
                print(out)
    else:
        # Just fetch the PR
        cmd_fetch_pr(
            argparse.Namespace(
                pr_or_url=parsed["pr"], fields=None, format="human"
            )
        )


def json_to_md(data, depth=0):
    """Recursively convert JSON to markdown formatted output.
    
    - dict → # headers (depth-based)
    - list → bullet points
    - scalar → plain value
    """
    prefix = "#" * (depth + 1)
    bullet = "  " * depth + "- "
    lines = []

    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key).replace("_", " ").replace("-", " ").title()
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix} {key_str}")
                lines.append(json_to_md(value, depth + 1))
            else:
                lines.append(f"{prefix} {key_str}")
                lines.append(str(value) if value is not None else "(null)")
    elif isinstance(data, list):
        if not data:
            lines.append(f"{bullet}(empty)")
        elif all(not isinstance(item, (dict, list)) for item in data):
            for item in data:
                lines.append(f"{bullet}{item}")
        else:
            for i, item in enumerate(data):
                if i > 0:
                    lines.append("---")
                lines.append(json_to_md(item, depth))
    else:
        lines.append(str(data))

    return "\n".join(lines)


def cmd_fields(args):
    """List available JSON fields for gh CLI commands."""
    topic = args.topic or "pr"
    if topic == "pr":
        # Trigger an error to get the field list from gh itself
        out, err, rc = run(["gh", "pr", "view", "0", "--json", "__invalid__"])
        # Parse the "Available fields:" section from stderr
        if "Available fields:" in err:
            lines = err.splitlines()
            in_fields = False
            print("Available fields for `gh pr view --json`:")
            for line in lines:
                if "Available fields:" in line:
                    in_fields = True
                    continue
                if in_fields and line.strip():
                    print(f"  {line.strip()}")
        else:
            print("[FAIL] Could not fetch field list.", file=sys.stderr)
            sys.exit(1)
    elif topic == "repo":
        out, err, rc = run(["gh", "repo", "view", ".", "--json", "__invalid__"])
        if "Available fields:" in err:
            lines = err.splitlines()
            in_fields = False
            print("Available fields for `gh repo view --json`:")
            for line in lines:
                if "Available fields:" in line:
                    in_fields = True
                    continue
                if in_fields and line.strip():
                    print(f"  {line.strip()}")
        else:
            print("[FAIL] Could not fetch field list.", file=sys.stderr)
            sys.exit(1)
    elif topic == "prs":
        out, err, rc = run(["gh", "pr", "list", "--json", "__invalid__"])
        if "Available fields:" in err:
            lines = err.splitlines()
            in_fields = False
            print("Available fields for `gh pr list --json`:")
            for line in lines:
                if "Available fields:" in line:
                    in_fields = True
                    continue
                if in_fields and line.strip():
                    print(f"  {line.strip()}")
        else:
            print("[FAIL] Could not fetch field list.", file=sys.stderr)
            sys.exit(1)
    elif topic == "issue":
        out, err, rc = run(["gh", "issue", "view", "0", "--json", "__invalid__"])
        if "Available fields:" in err:
            lines = err.splitlines()
            in_fields = False
            print("Available fields for `gh issue view --json`:")
            for line in lines:
                if "Available fields:" in line:
                    in_fields = True
                    continue
                if in_fields and line.strip():
                    print(f"  {line.strip()}")
        else:
            print("[FAIL] Could not fetch field list.", file=sys.stderr)
            sys.exit(1)
    elif topic == "issues":
        out, err, rc = run(["gh", "issue", "list", "--json", "__invalid__"])
        if "Available fields:" in err:
            lines = err.splitlines()
            in_fields = False
            print("Available fields for `gh issue list --json`:")
            for line in lines:
                if "Available fields:" in line:
                    in_fields = True
                    continue
                if in_fields and line.strip():
                    print(f"  {line.strip()}")
        else:
            print("[FAIL] Could not fetch field list.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[FAIL] Unknown topic: {topic}. Use: pr, prs, repo, issue, issues", file=sys.stderr)
        sys.exit(1)


def cmd_cmd(args):
    """Run any raw gh command and auto-format the output."""
    gh_args = args.gh_args
    cmd = ["gh"] + gh_args
    out, err, rc = run(cmd)
    if rc != 0:
        print(f"[FAIL] gh {' '.join(gh_args)} failed: {err}", file=sys.stderr)
        sys.exit(1)
    if not out:
        print(err or "(no output)")
        return
    if args.format == "raw":
        print(out)
        return
    # Try JSON parse and format
    try:
        data = json.loads(out)
        if args.format == "json":
            print(out)
            return
        print(json_to_md(data))
    except (json.JSONDecodeError, ValueError):
        if args.format == "json":
            print("[FAIL] gh returned malformed JSON", file=sys.stderr)
            sys.exit(1)
        # Not JSON — print raw
        print(out)


# ─── Issue Commands ─────────────────────────────────────────────

def cmd_fetch_issue(args):
    """Fetch and display issue details."""
    issue_num, url_repo = parse_issue_input(args.issue_num)
    current_repo = get_owner_repo()
    if url_repo and url_repo.lower() != current_repo.lower():
        print(
            f"[FAIL] Refusing issue URL from foreign repository: {url_repo}",
            file=sys.stderr,
        )
        sys.exit(1)
    issue_repo = url_repo or current_repo
    fields = args.fields or "number,title,state,author,body,createdAt,updatedAt,closedAt,labels,assignees,milestone,comments,url"
    out, err, rc = run(
        ["gh", "issue", "view", issue_num, "--json", fields, "--repo", issue_repo]
    )
    if rc != 0:
        print(f"[FAIL] Could not fetch issue #{issue_num}: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(out)
        if not isinstance(data, dict):
            raise TypeError
        if args.format in ("json", "raw"):
            print(out)
            return
        if args.fields:
            print(json_to_md(data))
            return

        print(f"#{data['number']} — {data['title']}")
        print("---")
        print(f"State: {data['state'].upper()}")
        print(f"Author: {data.get('author', {}).get('login', '?')}")
        print(f"Created: {data.get('createdAt', '?')}")
        print(f"Updated: {data.get('updatedAt', '?')}")
        if data.get('closedAt'):
            print(f"Closed: {data['closedAt']}")
        if data.get('url'):
            print(f"URL: {data['url']}")
        labels = data.get('labels', [])
        if labels:
            print(f"Labels: {', '.join(label.get('name', '') for label in labels)}")
        assignees = data.get('assignees', [])
        if assignees:
            print(f"Assignees: {', '.join(a.get('login', '') for a in assignees)}")
        milestone = data.get('milestone')
        if milestone:
            print(f"Milestone: {milestone.get('title', '')}")
        print(f"Comments: {data.get('comments', 0)}")
        print("---")
        body = data.get('body', '')
        print("Body:")
        if body:
            print(body)
        else:
            print("(no body)")
    except (json.JSONDecodeError, KeyError, TypeError):
        print(
            f"[FAIL] GitHub returned malformed JSON for issue #{issue_num}",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_fetch_issues(args):
    """List issues with optional filters."""
    cmd = ["gh", "issue", "list", "--json",
           "number,title,state,author,createdAt,updatedAt,labels,assignees"]
    if args.state:
        cmd.extend(["--state", args.state])
    if args.label:
        cmd.extend(["--label", args.label])
    if args.assignee:
        cmd.extend(["--assignee", args.assignee])
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])

    out, err, rc = run(cmd)
    if rc != 0:
        print(f"[FAIL] Could not list issues: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        issues = json.loads(out)
        if not issues:
            print("No issues found matching the given criteria.")
            return
        print(f"Issues matching: {len(issues)} result(s)")
        print()
        for issue in issues:
            state_tag = issue["state"].upper()
            labels_str = ""
            labels = issue.get("labels", [])
            if labels:
                labels_str = f" [{', '.join(label.get('name', '') for label in labels)}]"
            print(f"  #{issue['number']} ({state_tag}){labels_str} — {issue['title']}")
            print(f"       by {issue['author']['login']} — Created: {issue['createdAt']}")
    except json.JSONDecodeError:
        print(out)


def cmd_create_issue(args):
    """Create a new GitHub issue."""
    title = args.title
    body_file = args.body_file

    if not check_file(body_file):
        sys.exit(1)

    body = open(body_file).read()
    actor = None if args.unclaimed else authenticated_login()
    data = {"title": title, "body": body}
    if args.label:
        data["labels"] = [label.strip() for label in args.label.split(",")]
    requested = [a.strip() for a in args.assignee.split(",")] if args.assignee else []
    assignees = [*requested, *([actor] if actor else [])]
    if assignees:
        data["assignees"] = list(dict.fromkeys(assignees))

    with generated_payload("gh-create-issue-", data) as tf:
        OWNER_REPO = get_owner_repo()
        cmd = ["gh", "api", f"repos/{OWNER_REPO}/issues", "--method", "POST", "--input", str(tf)]
        out, err, rc = run(cmd)
    if rc != 0:
        print(f"[FAIL] Issue creation failed: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        issue_data = json.loads(out)
        number = issue_data["number"]
        url = issue_data["html_url"]
        if not isinstance(number, int) or not isinstance(url, str) or not url:
            raise KeyError("invalid issue response")
        if args.format == "json":
            print(json.dumps({"number": number, "url": url}, separators=(",", ":")))
            return
        print(f"[OK] Issue created: {issue_data.get('html_url', '')}")
        print(f"       #{issue_data.get('number', '')} — {issue_data.get('title', '')}")
    except (json.JSONDecodeError, KeyError):
        print("[FAIL] GitHub returned malformed issue creation JSON", file=sys.stderr)
        sys.exit(1)


def _json_response(content, description):
    """Return a GitHub JSON response or stop before a dependent write."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"[FAIL] GitHub returned malformed {description} JSON", file=sys.stderr)
        sys.exit(1)


def _specs_result(issue, action):
    """Return one validated Specs issue result."""
    try:
        result = {"action": action, "number": issue["number"], "url": issue["html_url"]}
        if not isinstance(result["number"], int) or not isinstance(result["url"], str):
            raise TypeError
    except (KeyError, TypeError):
        print("[FAIL] GitHub returned malformed Specs issue JSON", file=sys.stderr)
        sys.exit(1)
    return result


def _print_specs_result(result, output_format):
    """Render one validated Specs issue result."""
    if output_format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"[OK] Specs issue {result['action']}: {result['url']}")


def _has_primary_issue_marker(body, primary):
    """Return whether body has exactly one canonical primary issue marker."""
    markers = (
        re.findall(r"(?m)^Primary Issue: #([1-9][0-9]*)$", body)
        if isinstance(body, str)
        else []
    )
    return markers == [str(primary)]


def _issue_labels(issue, description):
    """Return validated labels from one GitHub issue response."""
    labels = issue.get("labels") if isinstance(issue, dict) else None
    if not isinstance(labels, list) or any(
        not isinstance(label, dict) or not isinstance(label.get("name"), str)
        for label in labels
    ):
        print(f"[FAIL] GitHub returned malformed {description} issue JSON", file=sys.stderr)
        sys.exit(1)
    return {label["name"] for label in labels}


def _validate_primary_specs_issue(primary):
    """Fetch and validate a primary issue before Specs mutations."""
    issue, error, code = api("GET", f"issues/{primary}")
    if code:
        print(f"[FAIL] Could not fetch primary issue: {error}", file=sys.stderr)
        sys.exit(1)
    issue_data = _json_response(issue, "primary issue")
    if not isinstance(issue_data, dict):
        print("[FAIL] GitHub returned malformed primary issue JSON", file=sys.stderr)
        sys.exit(1)
    if issue_data.get("state") != "open":
        print("[FAIL] Primary issue must be open", file=sys.stderr)
        sys.exit(1)
    if "pull_request" in issue_data:
        print("[FAIL] Primary issue must not be a pull request", file=sys.stderr)
        sys.exit(1)
    labels = _issue_labels(issue_data, "primary")
    if "roadmap" in labels:
        print("[FAIL] Primary issue must not be roadmap", file=sys.stderr)
        sys.exit(1)
    if "spec" in labels:
        print("[FAIL] Primary issue must not be spec", file=sys.stderr)
        sys.exit(1)
    body = issue_data.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        print("[FAIL] GitHub returned malformed primary issue JSON", file=sys.stderr)
        sys.exit(1)
    return re.findall(r"(?m)^Specs: #([1-9][0-9]*)\s*$", body)


def _link_primary_specs_issue(primary, specs_number):
    """Add the canonical Specs reference to the primary issue once."""
    issue, error, code = api("GET", f"issues/{primary}")
    if code:
        print(f"[FAIL] Could not fetch primary issue: {error}", file=sys.stderr)
        sys.exit(1)
    issue_data = _json_response(issue, "primary issue")
    body = issue_data.get("body") if isinstance(issue_data, dict) else None
    if body is None:
        body = ""
    if not isinstance(body, str):
        print("[FAIL] GitHub returned malformed primary issue JSON", file=sys.stderr)
        sys.exit(1)
    references = re.findall(r"(?m)^Specs: #([1-9][0-9]*)\s*$", body)
    if references == [str(specs_number)]:
        return
    if references:
        print("[FAIL] Primary issue already links a different or duplicate Specs issue", file=sys.stderr)
        sys.exit(1)
    _, error, code = api(
        "PATCH", f"issues/{primary}", {"body": f"{body.rstrip()}\n\nSpecs: #{specs_number}\n"}
    )
    if code:
        print(f"[FAIL] Could not link primary issue to Specs issue: {error}", file=sys.stderr)
        sys.exit(1)


def cmd_specs_ensure(args):
    """Create or reuse the single open Specs issue for one implementation issue."""
    primary, url_repo = parse_issue_input(args.primary)
    if url_repo and url_repo.lower() != get_owner_repo().lower():
        print(
            f"[FAIL] Refusing issue URL from foreign repository: {url_repo}",
            file=sys.stderr,
        )
        sys.exit(1)
    if int(primary) < 1 or not args.title.strip():
        print("[FAIL] Specs issue inputs must be valid", file=sys.stderr)
        sys.exit(1)
    primary_references = _validate_primary_specs_issue(primary)
    title = f"Spec: {args.title.strip()}"
    labels, error, code = api("GET", "labels?per_page=100", paginate=True)
    if code:
        print(f"[FAIL] Could not inspect repository labels: {error}", file=sys.stderr)
        sys.exit(1)
    label_data = _json_response(labels, "label")
    if not isinstance(label_data, list):
        print("[FAIL] GitHub returned malformed label JSON", file=sys.stderr)
        sys.exit(1)
    has_spec = any(
        label.get("name") == "spec" for label in label_data if isinstance(label, dict)
    )
    issues, error, code = api(
        "GET", "issues?state=open&labels=spec&per_page=100", paginate=True
    )
    if code:
        print(f"[FAIL] Could not inspect Specs issues: {error}", file=sys.stderr)
        sys.exit(1)
    issue_data = _json_response(issues, "Specs issue")
    if not isinstance(issue_data, list):
        print("[FAIL] GitHub returned malformed Specs issue JSON", file=sys.stderr)
        sys.exit(1)
    candidates = [
        issue
        for issue in issue_data
        if isinstance(issue, dict)
        and "pull_request" not in issue
        and issue.get("title") == title
    ]
    if any(
        isinstance(issue.get("body"), str)
        and len(re.findall(r"(?m)^Primary Issue: #[1-9][0-9]*$", issue["body"])) > 1
        for issue in candidates
    ):
        print("[FAIL] Specs issue has ambiguous primary issue markers", file=sys.stderr)
        sys.exit(1)
    matches = [
        issue
        for issue in candidates
        if _has_primary_issue_marker(issue.get("body"), primary)
    ]
    if len(matches) > 1:
        print("[FAIL] Found multiple matching open Specs issues", file=sys.stderr)
        sys.exit(1)
    if matches:
        result = _specs_result(matches[0], "reused")
        _link_primary_specs_issue(primary, result["number"])
        _print_specs_result(result, args.format)
        return
    if primary_references:
        print(
            "[FAIL] Primary issue already links a different or duplicate Specs issue",
            file=sys.stderr,
        )
        sys.exit(1)
    if not has_spec:
        _, error, code = api(
            "POST",
            "labels",
            {"name": "spec", "color": "0E8A16", "description": "Planning record"},
        )
        if code:
            print(f"[FAIL] Could not create spec label: {error}", file=sys.stderr)
            sys.exit(1)
    body = f"# Specs: {args.title.strip()}\n\nPrimary Issue: #{primary}\n"
    created, error, code = api(
        "POST", "issues", {"title": title, "body": body, "labels": ["spec"]}
    )
    if code:
        print(f"[FAIL] Could not create Specs issue: {error}", file=sys.stderr)
        sys.exit(1)
    result = _specs_result(_json_response(created, "Specs issue"), "created")
    _link_primary_specs_issue(primary, result["number"])
    _print_specs_result(result, args.format)


def _specs_document(path, name):
    """Read one complete canonical document after repository-bound validation."""
    if not check_file(path):
        sys.exit(1)
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        print(f"[FAIL] Could not read {name} document: {error}", file=sys.stderr)
        sys.exit(1)
    return f"## {name.title()}\n\n{content}"


def _specs_index(body, documents):
    """Render the immutable four-document index after initialization."""
    base = re.sub(
        r"\n+\*\*Current Revision\*\*: none\s*\n+## Revision History\s*\Z",
        "",
        body,
    )
    links = "".join(f"- {name}: {documents[name]}\n" for name in _SPECS_DOCUMENTS)
    return f"{base.rstrip()}\n\n## Documents\n\n{links}"


_SPECS_DOCUMENTS = ("spec", "design", "plan", "task")
_SPECS_LEGACY_LABELS = {
    "spec": "Spec",
    "design": "Design",
    "plan": "Implementation Plan",
    "task": "Tasks",
}


def _specs_comment_id(url, number, repository):
    """Validate one indexed comment URL and return its comment ID."""
    match = re.fullmatch(
        r"https://github\.com/([^/]+/[^/]+)/issues/([1-9][0-9]*)"
        r"#issuecomment-([1-9][0-9]*)",
        url if isinstance(url, str) else "",
        re.I,
    )
    if (
        not match
        or match.group(1).lower() != repository.lower()
        or int(match.group(2)) != number
    ):
        print(
            "[FAIL] Specs index contains a malformed or foreign link", file=sys.stderr
        )
        sys.exit(1)
    return match.group(3)


def _validate_specs_references(references, number, repository):
    """Validate complete, unique references for the current Specs issue."""
    if list(references) != list(_SPECS_DOCUMENTS):
        print(
            "[FAIL] Specs index must contain exactly four document keys",
            file=sys.stderr,
        )
        sys.exit(1)
    ids = [_specs_comment_id(url, number, repository) for url in references.values()]
    if len(set(ids)) != len(ids):
        print("[FAIL] Specs index contains duplicate comment links", file=sys.stderr)
        sys.exit(1)
    return references


def _specs_references(body, number, repository):
    """Parse the strict index or the shipped current-document link block."""
    document_markers = re.findall(r"(?m)^## Documents\s*$", body)
    if document_markers:
        match = re.search(r"(?ms)^## Documents\n\n((?:- [^\n]+\n)+)\Z", body)
        if len(document_markers) != 1 or not match:
            print("[FAIL] Specs issue has a malformed document index", file=sys.stderr)
            sys.exit(1)
        entries = re.findall(r"(?m)^- ([a-z]+): (https://[^\s]+)$", match.group(1))
        if len(entries) != len(_SPECS_DOCUMENTS):
            print("[FAIL] Specs issue has a malformed document index", file=sys.stderr)
            sys.exit(1)
        return _validate_specs_references(dict(entries), number, repository)

    if re.fullmatch(
        r"# Specs: [^\n]+\n\nPrimary Issue: #[1-9][0-9]*\n"
        r"(?:\n\*\*Current Revision\*\*: none\n\n## Revision History\n)?",
        body,
    ):
        return None
    revision_markers = re.findall(
        r"(?m)^\*\*Current Revision\*\*: (none|[1-9][0-9]*)\s*$", body
    )
    legacy_lines = re.findall(
        r"(?m)^- \*\*(Spec|Design|Implementation Plan|Tasks)\*\*: ", body
    )
    if len(revision_markers) != 1 or revision_markers[0] == "none":
        print(
            "[FAIL] Specs issue has a malformed current-document index", file=sys.stderr
        )
        sys.exit(1)
    pattern = r"(?m)^\*\*Current Revision\*\*: [1-9][0-9]*\n" + "\n".join(
        rf"- \*\*{re.escape(label)}\*\*: \[{re.escape(label)}\]\((https://[^\s)]+)\)$"
        for label in _SPECS_LEGACY_LABELS.values()
    )
    match = re.search(pattern, body)
    if not match or len(legacy_lines) != len(_SPECS_DOCUMENTS):
        print(
            "[FAIL] Specs issue has a malformed current-document index", file=sys.stderr
        )
        sys.exit(1)
    references = dict(zip(_SPECS_DOCUMENTS, match.groups(), strict=True))
    return _validate_specs_references(references, number, repository)


def _specs_comment_url(comment, number, repository):
    """Return one validated Specs comment URL."""
    url = comment.get("html_url") if isinstance(comment, dict) else None
    _specs_comment_id(url, number, repository)
    return url


def _specs_comment_content(body, name):
    """Return document content from canonical or legacy comment wrappers."""
    canonical = f"## {name.title()}\n\n"
    if body.startswith(canonical):
        return body.removeprefix(canonical)
    match = re.match(rf"## Revision [1-9][0-9]*: {name.title()}\n\n", body)
    return body[match.end() :] if match else None


def _specs_publish_context(args):
    """Validate the target Specs issue before reading documents or writing."""
    if args.number < 1 or args.primary < 1 or args.revision < 1:
        print("[FAIL] Specs issue inputs must be positive", file=sys.stderr)
        sys.exit(1)
    issue, error, code = api("GET", f"issues/{args.number}")
    if code:
        print(f"[FAIL] Could not fetch Specs issue: {error}", file=sys.stderr)
        sys.exit(1)
    issue_data = _json_response(issue, "Specs issue")
    if not isinstance(issue_data, dict) or issue_data.get("state") != "open":
        print("[FAIL] Specs issue must be open", file=sys.stderr)
        sys.exit(1)
    if "pull_request" in issue_data:
        print("[FAIL] Specs issue must not be a pull request", file=sys.stderr)
        sys.exit(1)
    if "spec" not in _issue_labels(issue_data, "Specs"):
        print("[FAIL] Specs issue must be labelled spec", file=sys.stderr)
        sys.exit(1)
    body = issue_data.get("body")
    if not _has_primary_issue_marker(body, args.primary):
        print("[FAIL] Specs issue does not identify the primary issue", file=sys.stderr)
        sys.exit(1)
    repository = get_owner_repo()
    references = _specs_references(body, args.number, repository)
    return body, repository, references


def _specs_comments(number):
    """Fetch the complete validated Specs comment list."""
    comments, error, code = api(
        "GET", f"issues/{number}/comments?per_page=100", paginate=True
    )
    if code:
        print(f"[FAIL] Could not inspect Specs comments: {error}", file=sys.stderr)
        sys.exit(1)
    comment_data = _json_response(comments, "Specs comment")
    if not isinstance(comment_data, list):
        print("[FAIL] GitHub returned malformed Specs comment JSON", file=sys.stderr)
        sys.exit(1)
    return comment_data


def _initialize_specs(number, body, repository, documents, comments):
    """Resume initialization, create missing comments, and write the index once."""
    references = {}
    for name, content in documents.items():
        heading = f"## {name.title()}\n\n"
        matching = [
            comment
            for comment in comments
            if isinstance(comment, dict)
            and isinstance(comment.get("body"), str)
            and comment["body"].startswith(heading)
        ]
        if len(matching) > 1 or (matching and matching[0]["body"] != content):
            print(
                "[FAIL] Specs initialization has conflicting comments", file=sys.stderr
            )
            sys.exit(1)
        if matching:
            references[name] = _specs_comment_url(matching[0], number, repository)
    for name, content in documents.items():
        if name in references:
            continue
        comment, error, code = api(
            "POST", f"issues/{number}/comments", {"body": content}
        )
        if code:
            print(f"[FAIL] Could not publish {name} document: {error}", file=sys.stderr)
            sys.exit(1)
        references[name] = _specs_comment_url(
            _json_response(comment, "Specs comment"), number, repository
        )
    _, error, code = api(
        "PATCH", f"issues/{number}", {"body": _specs_index(body, references)}
    )
    if code:
        print(f"[FAIL] Could not initialize Specs index: {error}", file=sys.stderr)
        sys.exit(1)
    return references


def _update_specs(number, repository, references, documents, comments):
    """Resolve every indexed comment before editing changed document bodies."""
    resolved = {}
    for name, url in references.items():
        matching = [
            comment
            for comment in comments
            if isinstance(comment, dict) and comment.get("html_url") == url
        ]
        if len(matching) != 1 or not isinstance(matching[0].get("body"), str):
            print("[FAIL] Specs index references a missing comment", file=sys.stderr)
            sys.exit(1)
        resolved[name] = matching[0]
    for name, comment in resolved.items():
        desired_content = documents[name].split("\n\n", 1)[1]
        if _specs_comment_content(comment["body"], name) == desired_content:
            continue
        comment_id = _specs_comment_id(references[name], number, repository)
        _, error, code = api(
            "PATCH", f"issues/comments/{comment_id}", {"body": documents[name]}
        )
        if code:
            print(f"[FAIL] Could not update {name} document: {error}", file=sys.stderr)
            sys.exit(1)
    return references


def cmd_specs_publish(args):
    """Initialize or update four stable indexed Specs comments."""
    body, repository, references = _specs_publish_context(args)
    documents = {
        name: _specs_document(getattr(args, name), name) for name in _SPECS_DOCUMENTS
    }
    comments = _specs_comments(args.number)
    if references is None:
        references = _initialize_specs(
            args.number, body, repository, documents, comments
        )
    else:
        references = _update_specs(
            args.number, repository, references, documents, comments
        )
    result = {"number": args.number, "revision": args.revision, "documents": references}
    print(
        json.dumps(result, sort_keys=True)
        if args.format == "json"
        else "[OK] Published indexed Specs documents"
    )


def cmd_update_issue_body(args):
    """Update an issue body."""
    issue_num = args.issue_num
    body_file = args.body_file

    if not check_file(body_file):
        sys.exit(1)

    out, err, rc = api("PATCH", f"issues/{issue_num}", {"body": open(body_file).read()})
    if rc != 0:
        print(f"[FAIL] Issue body update failed: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Issue #{issue_num} body updated")


def cmd_update_issue_title(args):
    """Update an issue title."""
    issue_num = args.issue_num
    title = args.title
    out, err, rc = api("PATCH", f"issues/{issue_num}", {"title": title})
    if rc != 0:
        print(f"[FAIL] Issue title update failed: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] Issue #{issue_num} title updated to: {title}")


# ─── Argument Parser ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GitHub PR, review, and issue helper")
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch pr
    p = sub.add_parser("fetch", help="Fetch PR info or URL resource")
    fetch_sub = p.add_subparsers(dest="fetch_type", required=True)
    fp = fetch_sub.add_parser("pr", help="Fetch PR details (curated output)")
    fp.add_argument("pr_or_url", help="PR number or URL")
    fp.add_argument("--json", dest="fields", type=str, default=None,
                    help="Custom JSON fields (default: curated useful fields)")
    fp.add_argument("--format", choices=["human", "json", "raw"], default="human")
    fp.set_defaults(func=cmd_fetch_pr)
    
    fc = fetch_sub.add_parser("comments", help="Fetch PR comments and reviews")
    fc.add_argument("pr_or_url", help="PR number or URL")
    fc.add_argument("--output", type=str, default=None, help="Write formatted report to this file (default: reviews/remote/REVIEW_<normalized_branch>_fetched_<ts>.md; branch slashes become underscores)")
    fc.add_argument("--all", action="store_true", help="Include minimized/resolved comments (default: skip them)")
    fc.add_argument("--urls-only", action="store_true", help="Output JSON lines of filtered comment URLs only (for preflight consumption)")
    fc.set_defaults(func=cmd_fetch_comments)

    frs = fetch_sub.add_parser(
        "review-state", help="Fetch authoritative review cleanup state as JSON"
    )
    frs.add_argument("pr_or_url", help="PR number or URL")
    frs.set_defaults(func=cmd_fetch_review_state)
    
    fu = fetch_sub.add_parser("url", help="Fetch a specific comment/review from its full URL")
    fu.add_argument("url", help="Full GitHub URL (e.g., https://github.com/.../pull/11#issue-4399302650)")
    fu.set_defaults(func=cmd_fetch_url)
    
    fprs = fetch_sub.add_parser("prs", help="List PRs with optional filters")
    fprs.add_argument("--head", type=str, default=None, help="Filter by head branch")
    fprs.add_argument("--state", type=str, default=None, choices=["open", "closed", "merged"], help="Filter by state (default: open)")
    fprs.add_argument("--base", type=str, default=None, help="Filter by base branch")
    fprs.add_argument("--limit", type=int, default=None, help="Max results (default: 30)")
    fprs.set_defaults(func=cmd_fetch_prs)

    frepo = fetch_sub.add_parser("repo", help="Fetch repository information")
    frepo.set_defaults(func=cmd_fetch_repo)

    fi = fetch_sub.add_parser("issue", help="Fetch issue details (curated output)")
    fi.add_argument("issue_num", help="Issue number")
    fi.add_argument("--json", dest="fields", type=str, default=None,
                    help="Custom JSON fields (default: curated useful fields)")
    fi.add_argument("--format", choices=["human", "json", "raw"], default="human")
    fi.set_defaults(func=cmd_fetch_issue)

    fis = fetch_sub.add_parser("issues", help="List issues with optional filters")
    fis.add_argument("--state", type=str, default=None, choices=["open", "closed", "all"],
                     help="Filter by state (default: open)")
    fis.add_argument("--label", type=str, default=None, help="Filter by label name")
    fis.add_argument("--assignee", type=str, default=None, help="Filter by assignee login")
    fis.add_argument("--limit", type=int, default=None, help="Max results (default: 30)")
    fis.set_defaults(func=cmd_fetch_issues)


    # post review
    p = sub.add_parser("post", help="Post review or comment")
    post_sub = p.add_subparsers(dest="post_type", required=True)
    pr_review = post_sub.add_parser("review", help="Post a PR review")
    pr_review.add_argument("pr_or_url", help="PR number or URL")
    pr_review.add_argument("body_file", help="Path to markdown file with review body")
    pr_review.add_argument("comments_file", nargs="?", default=None, help="Optional path to JSON file with inline comments")
    pr_review.add_argument("--event", choices=["APPROVE", "COMMENT", "REQUEST_CHANGES"], default="COMMENT")
    pr_review.set_defaults(func=cmd_post_review)
    
    pr_comment = post_sub.add_parser("comment", help="Post a general PR comment (not on a file)")
    pr_comment.add_argument("pr_or_url", help="PR number or URL")
    pr_comment.add_argument("body_file", help="Path to markdown file with comment body")
    pr_comment.set_defaults(func=cmd_post_comment)
    
    pr_inline = post_sub.add_parser("inline", help="Post an inline comment on a specific file/line")
    pr_inline.add_argument("pr_or_url", help="PR number or URL")
    pr_inline.add_argument("body_file", help="Path to markdown file with comment body")
    pr_inline.add_argument("--path", required=True, help="File path to comment on")
    pr_inline.add_argument("--line", required=True, type=int, help="Line number in the PR diff")
    pr_inline.add_argument("--side", choices=["LEFT", "RIGHT"], default="RIGHT", help="Side of the diff")
    pr_inline.add_argument("--start-line", type=int, default=None, help="Start line for multi-line comment")
    pr_inline.add_argument("--start-side", choices=["LEFT", "RIGHT"], default=None, help="Start side for multi-line")
    pr_inline.set_defaults(func=cmd_post_inline_comment)
    
    pr_reply = post_sub.add_parser("reply", help="Reply to an existing review thread")
    pr_reply.add_argument("pr_or_url", help="PR number or URL")
    pr_reply.add_argument("comment_id", help="Comment ID to reply to")
    pr_reply.add_argument("body_file", help="Path to markdown file with reply body")
    pr_reply.set_defaults(func=cmd_reply_comment)
    
    # resolve comment
    p = sub.add_parser("resolve", help="Resolve a review thread")
    p.add_argument("pr_or_url", help="PR number or URL")
    p.add_argument("comment_id", help="Comment ID or full URL to resolve (e.g. 12345 or ...#discussion_r12345)")
    p.set_defaults(func=cmd_resolve_comment)
    
    p = sub.add_parser("minimize", help="Minimize (hide) a PR comment or review body with a reason classifier")
    p.add_argument("pr_or_url", help="PR number or URL")
    p.add_argument("comment_id", help="Comment ID, review ID, or full URL (e.g. 12345, ...#discussion_r12345, ...#pullrequestreview-67890)")
    p.add_argument("--classifier", choices=["RESOLVED", "OUTDATED", "DUPLICATE"], default="OUTDATED", help="Reason for minimizing")
    p.set_defaults(func=cmd_minimize_comment)
    
    # unminimize comment
    p = sub.add_parser("unminimize", help="Restore a previously minimized PR comment")
    p.add_argument("pr_or_url", help="PR number or URL")
    p.add_argument("comment_id", help="Comment ID or full URL to restore")
    p.set_defaults(func=cmd_unminimize_comment)
    
    # batch close
    p = sub.add_parser("batch", help="Batch operations")
    batch_sub = p.add_subparsers(dest="batch_type", required=True)
    bm = batch_sub.add_parser("close", help="Batch close multiple PR comments from a JSON file (resolves inline, minimizes non-inline)")
    bm.add_argument("pr_or_url", help="PR number or URL")
    bm.add_argument("json_file", help="Path to JSON: [{\"url\": \".../...#discussion_r<id>\"}, {\"url\": \".../...#pullrequestreview<id>\", \"classifier\": \"OUTDATED\"}]")
    bm.set_defaults(func=cmd_batch_close)
    
    # update body
    p = sub.add_parser("update", help="Update PR or issue")
    update_sub = p.add_subparsers(dest="update_type", required=True)
    ub = update_sub.add_parser("body", help="Update PR body")
    ub.add_argument("pr_or_url", help="PR number or URL")
    ub.add_argument("body_file", help="Path to markdown file with new body")
    ub.set_defaults(func=cmd_update_body)
    ut = update_sub.add_parser("title", help="Update PR title")
    ut.add_argument("pr_or_url", help="PR number or URL")
    ut.add_argument("title", help="New PR title")
    ut.set_defaults(func=cmd_update_title)

    # Issue sub-commands under update
    ui = update_sub.add_parser("issue", help="Update an issue")
    issue_sub = ui.add_subparsers(dest="issue_update_type", required=True)
    iub = issue_sub.add_parser("body", help="Update issue body")
    iub.add_argument("issue_num", help="Issue number")
    iub.add_argument("body_file", help="Path to markdown file with new body")
    iub.set_defaults(func=cmd_update_issue_body)
    iut = issue_sub.add_parser("title", help="Update issue title")
    iut.add_argument("issue_num", help="Issue number")
    iut.add_argument("title", help="New issue title")
    iut.set_defaults(func=cmd_update_issue_title)
    
    # fields — list available JSON fields
    p = sub.add_parser("fields", help="List available JSON fields for gh commands")
    p.add_argument("topic", nargs="?", default="pr", choices=["pr", "prs", "repo", "issue", "issues"],
                   help="Topic: pr (default), prs, repo, issue, issues")
    p.set_defaults(func=cmd_fields)

    # interact — URL-based interaction
    p = sub.add_parser("interact", help="Interact with a PR comment or review by URL")
    interact_sub = p.add_subparsers(dest="interact_action", required=True)
    
    ia_min = interact_sub.add_parser("minimize", help="Minimize (hide) a comment or review body by URL")
    ia_min.add_argument("url", help="Full GitHub URL (e.g. .../pull/26#discussion_r12345 or .../pull/26#pullrequestreview-67890)")
    ia_min.add_argument("--classifier", choices=["RESOLVED", "OUTDATED", "DUPLICATE"], default="OUTDATED")
    ia_min.set_defaults(func=cmd_handle_minimize)
    
    ia_res = interact_sub.add_parser("resolve", help="Resolve an inline comment thread by URL")
    ia_res.add_argument("url", help="Full GitHub URL with #discussion_r")
    ia_res.set_defaults(func=cmd_handle_resolve)
    
    ia_unmin = interact_sub.add_parser("unminimize", help="Restore a minimized comment or review by URL")
    ia_unmin.add_argument("url", help="Full GitHub URL")
    ia_unmin.set_defaults(func=cmd_handle_unminimize)
    
    ia_reply = interact_sub.add_parser("reply", help="Reply to an inline comment thread by URL")
    ia_reply.add_argument("url", help="Full GitHub URL with #discussion_r")
    ia_reply.add_argument("body_file", help="Path to markdown body file")
    ia_reply.set_defaults(func=cmd_handle_reply)

    # cmd — wildcard raw gh runner
    p = sub.add_parser("cmd", help="Run any gh command with auto-formatted JSON output")
    p.add_argument("--format", choices=["human", "json", "raw"], default="human")
    p.add_argument("gh_args", nargs=argparse.REMAINDER, help="Raw gh arguments (e.g., pr view 10)")
    p.set_defaults(func=cmd_cmd)

    # create pr
    p = sub.add_parser("create", help="Create a PR")
    p.add_argument("title", help="PR title")
    p.add_argument("body_file", help="Path to markdown file with PR body")
    p.add_argument("--head", type=str, default=None, help="Head branch (defaults to current branch)")
    p.add_argument("--base", type=str, default=None, help="Base branch (auto-detected if not specified)")
    p.add_argument("--draft", action="store_true", help="Create as draft")
    p.add_argument("--format", choices=["human", "json"], default="human")
    p.set_defaults(func=cmd_create_pr)

    # create issue
    p = sub.add_parser("create-issue", help="Create an issue")
    p.add_argument("title", help="Issue title")
    p.add_argument("body_file", help="Path to markdown file with issue body")
    p.add_argument("--label", type=str, default=None, help="Comma-separated labels to apply")
    assignment = p.add_mutually_exclusive_group()
    assignment.add_argument("--assignee", type=str, default=None, help="Comma-separated assignees")
    assignment.add_argument("--unclaimed", action="store_true", help="Create without assignees")
    p.add_argument("--format", choices=["human", "json"], default="human")
    p.set_defaults(func=cmd_create_issue)

    p = sub.add_parser("specs", help="Create or reuse the Specs issue for a primary issue")
    specs_sub = p.add_subparsers(dest="specs_action", required=True)
    ensure = specs_sub.add_parser("ensure", help="Create or reuse one open Specs issue")
    ensure.add_argument("primary", help="Primary issue number or URL")
    ensure.add_argument("title", help="Primary issue title")
    ensure.add_argument("--format", choices=["human", "json"], default="human")
    ensure.set_defaults(func=cmd_specs_ensure)
    publish = specs_sub.add_parser(
        "publish", help="Initialize or update indexed Specs documents"
    )
    publish.add_argument("number", type=int, help="Specs issue number")
    publish.add_argument("--primary", type=int, required=True, help="Primary issue number")
    publish.add_argument("--revision", type=int, required=True)
    for name in ("spec", "design", "plan", "task"):
        publish.add_argument(f"--{name}", required=True)
    publish.add_argument("--format", choices=["human", "json"], default="human")
    publish.set_defaults(func=cmd_specs_publish)

    # claim issue or PR
    p = sub.add_parser("claim", help="Assign the authenticated user to an issue or PR")
    p.add_argument("number", type=int, help="Issue or PR number")
    p.add_argument("--format", choices=["human", "json"], default="human")
    p.set_defaults(func=cmd_claim)

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        parser.print_help()
        sys.exit(0)

    # If the first arg after script isn't a known command, show fallback message
    known = {"fetch", "post", "resolve", "minimize", "unminimize", "batch", "interact", "update", "create", "create-issue", "specs", "claim", "cmd", "fields"}
    if sys.argv[1] not in known:
        print(
            f"[FAIL] Unknown command. Use: gh.py cmd {' '.join(sys.argv[1:])}",
            file=sys.stderr,
        )
        sys.exit(2)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
