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

import json, os, re, subprocess, sys, time, urllib.parse, argparse
from datetime import datetime
from pathlib import Path

import repo_guard


TMP_DIR = Path("./tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)


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
        fm = re.match(r"(issue|pullrequestreview|discussionrereview)-(\d+)", frag)
        if fm:
            result["type"] = fm.group(1)
            result["id"] = fm.group(2)
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
    return out, err, rc


def clean_temp(path: str | Path):
    """Delete temp file if it exists."""
    p = Path(path)
    if p.exists():
        repo_guard.assert_inside_repo(p)
        p.unlink()


def check_file(path: str) -> bool:
    """Validate file exists and has content."""
    p = repo_guard.assert_inside_repo(path)
    if not p.exists():
        print(f"[FAIL] File not found: {path}", file=sys.stderr)
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
    owner_repo = get_owner_repo()
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
            print(f"Labels: {', '.join(l.get('name', '') for l in labels)}")
        
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
        print(out)


def cmd_fetch_comments(args):
    pr = parse_pr_input(args.pr_or_url)
    
    # Get PR info for branch name
    pr_info = {}
    out, err, rc = api("GET", f"pulls/{pr}")
    if rc == 0:
        try:
            pr_info = json.loads(out)
        except json.JSONDecodeError:
            pass
    branch = pr_info.get("head", {}).get("ref", f"PR-{pr}")
    base_sha = pr_info.get("base", {}).get("sha", "")
    head_sha = pr_info.get("head", {}).get("sha", "")
    safe_branch = branch.replace("/", "-")
    ts = int(time.time())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    out_dir = Path("reviews") / "remote"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(out_dir / f"REVIEW_{safe_branch}_fetched_{ts}.md")
    
    # Fetch all inline comments
    all_comments_raw = []
    out, err, rc = api("GET", f"pulls/{pr}/comments", paginate=True)
    if rc == 0:
        try:
            all_comments_raw = json.loads(out)
        except json.JSONDecodeError:
            pass
    
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
    
    # Fetch all reviews
    all_reviews = []
    out, err, rc = api("GET", f"pulls/{pr}/reviews", paginate=True)
    if rc == 0:
        try:
            all_reviews = json.loads(out)
        except json.JSONDecodeError:
            pass
    
    # Separate reviews that have a body (meaningful review) vs empty ones
    meaningful_reviews = [r for r in all_reviews if r.get("body", "").strip()]

    # Filter out minimized reviews (REST API doesn't reflect GraphQL minimization)
    if not include_minimized and meaningful_reviews:
        # Batch query GraphQL to check which reviews are minimized
        review_nodes = " ".join(f'_{i}: node(id: "{r["node_id"]}") {{ ... on PullRequestReview {{ isMinimized }} }}' for i, r in enumerate(meaningful_reviews[:50]))
        gql_query = f"query {{ {review_nodes} }}"
        cmd = ["gh", "api", "graphql", "-f", f"query={gql_query}"]
        gout, _, grc = run(cmd)
        if grc == 0 and gout:
            try:
                gdata = json.loads(gout)["data"]
                filtered = []
                for i, r in enumerate(meaningful_reviews):
                    key = f"_{i}"
                    is_minimized = gdata.get(key, {}).get("isMinimized", False)
                    if not is_minimized:
                        filtered.append(r)
                meaningful_reviews = filtered
            except (KeyError, json.JSONDecodeError):
                pass
    
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
        if c not in orphan_comments:
            continue
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
    
    output_path = str(repo_guard.assert_inside_repo(output_path))
    Path(output_path).write_text(report, encoding="utf-8")
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
        tf = TMP_DIR / f"gh-review-payload-{int(time.time())}.json"
        with open(tf, "w") as f:
            json.dump(payload, f)
        
        OWNER_REPO = get_owner_repo()
        cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/reviews",
               "--method", "POST", "--input", str(tf)]
        out, err, rc = run(cmd)
        clean_temp(tf)
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
            tf = TMP_DIR / f"gh-review-payload-{int(time.time())}.json"
            with open(tf, "w") as f:
                json.dump(payload, f)
            OWNER_REPO = get_owner_repo()
            cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/reviews",
                   "--method", "POST", "--input", str(tf)]
            out, err, rc = run(cmd)
            clean_temp(tf)
        else:
            data = {"body": body, "event": "COMMENT"}
            out, err, rc = api("POST", f"pulls/{pr}/reviews", data)
    
    if rc != 0:
        print(f"[FAIL] Review post failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    # Auto-clean temp files on success
    clean_temp(body_file)
    if comments_file:
        clean_temp(comments_file)
    
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
    print(f"")
    print(f"**PR Review URL**: {review_url}")
    print(f"")
    for e in comment_entries:
        loc = f"{e['path']}:{e['line']}"
        print(f"**PR Comment**: {e['url']}")
        print(f"**Location**: {loc}")
        for line in e['body'].split("\n"):
            print(f"  {line}")
        print(f"")


def cmd_post_comment(args):
    pr = parse_pr_input(args.pr_or_url)
    body_file = args.body_file
    
    if not check_file(body_file):
        sys.exit(1)
    
    out, err, rc = api("POST", f"issues/{pr}/comments", {"body": open(body_file).read()})
    if rc != 0:
        print(f"[FAIL] Comment post failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    clean_temp(body_file)
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
    
    clean_temp(body_file)
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
    import tempfile
    data = {
        "body": open(body_file).read(),
        "in_reply_to": int(comment_id)
    }
    tf = TMP_DIR / f"gh-reply-{int(time.time())}.json"
    with open(tf, "w") as f:
        json.dump(data, f)
    
    OWNER_REPO = get_owner_repo()
    cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls/{pr}/comments",
           "--method", "POST", "--input", str(tf)]
    out, err, rc = run(cmd)
    clean_temp(tf)
    
    if rc != 0:
        print(f"[FAIL] Reply failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    clean_temp(body_file)
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
        OWNER_REPO = get_owner_repo()
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
        OWNER_REPO = get_owner_repo()
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
    OWNER_REPO = get_owner_repo()
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
    query = f"""
    query {{
      repository(owner: "{owner_repo.split('/')[0]}", name: "{owner_repo.split('/')[1]}") {{
        pullRequest(number: {pr}) {{
          reviewThreads(first: 100) {{
            nodes {{
              id
              isResolved
              comments(first: 20) {{
                nodes {{
                  id
                  fullDatabaseId
                  isMinimized
                }}
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
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    out, err, rc = run(cmd)
    if rc != 0 or not out:
        return {}
    try:
        data = json.loads(out)
        nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (KeyError, json.JSONDecodeError):
        return {}

    thread_map = {}
    for t in nodes:
        tid = t["id"]
        is_resolved = t["isResolved"]
        for c in t["comments"]["nodes"]:
            cid = str(c.get("fullDatabaseId", ""))
            if cid:
                thread_map[cid] = {
                    "thread_id": tid,
                    "is_resolved": is_resolved,
                    "is_minimized": c.get("isMinimized", False),
                }
    return thread_map


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
                if child_ok > 0:
                    ok += 1
                else:
                    fail += 1

    print(f"[OK] Batch close done: {ok} succeeded, {fail} failed")


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
    
    clean_temp(body_file)
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

    # Get merge-base with main as baseline
    main_mb = ""
    try:
        main_mb = subprocess.check_output(["git", "merge-base", "main", branch], text=True, stderr=subprocess.DEVNULL).strip()
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
    
    data = {"title": title, "head": head, "base": base, "body": body}
    if args.draft:
        data["draft"] = True
    
    # Use JSON temp file to avoid -f multiline issues
    tf = TMP_DIR / f"gh-create-pr-{int(time.time())}.json"
    with open(tf, "w") as f:
        json.dump(data, f)
    
    OWNER_REPO = get_owner_repo()
    cmd = ["gh", "api", f"repos/{OWNER_REPO}/pulls", "--method", "POST", "--input", str(tf)]
    out, err, rc = run(cmd)
    clean_temp(tf)
    if rc != 0:
        print(f"[FAIL] PR creation failed: {err}", file=sys.stderr)
        sys.exit(1)
    
    clean_temp(body_file)
    try:
        pr_data = json.loads(out)
        print(f"[OK] PR created: {pr_data.get('html_url', '')} ({head} → {base})")
    except json.JSONDecodeError:
        print(out)


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
    owner_repo = get_owner_repo()
    
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
    owner_repo = get_owner_repo()
    
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
    tf = TMP_DIR / f"gh-reply-{int(time.time())}.json"
    with open(tf, "w") as f:
        json.dump(data, f)
    owner_repo = get_owner_repo()
    cmd = ["gh", "api", f"repos/{owner_repo}/pulls/{pr}/comments",
           "--method", "POST", "--input", str(tf)]
    out2, err2, rc2 = run(cmd)
    clean_temp(tf)
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
        cmd_fetch_pr(argparse.Namespace(pr_or_url=parsed["pr"]))


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
    # Try JSON parse and format
    try:
        data = json.loads(out)
        print(json_to_md(data))
    except (json.JSONDecodeError, ValueError):
        # Not JSON — print raw
        print(out)


# ─── Issue Commands ─────────────────────────────────────────────

def cmd_fetch_issue(args):
    """Fetch and display issue details."""
    issue_num = args.issue_num
    fields = args.fields or "number,title,state,author,body,createdAt,updatedAt,closedAt,labels,assignees,milestone,comments,url"
    out, err, rc = run(["gh", "issue", "view", issue_num, "--json", fields])
    if rc != 0:
        print(f"[FAIL] Could not fetch issue #{issue_num}: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(out)
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
            print(f"Labels: {', '.join(l.get('name', '') for l in labels)}")
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
    except json.JSONDecodeError:
        print(out)


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
                labels_str = f" [{', '.join(l.get('name', '') for l in labels)}]"
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
    data = {"title": title, "body": body}
    if args.label:
        data["labels"] = [l.strip() for l in args.label.split(",")]
    if args.assignee:
        data["assignees"] = [a.strip() for a in args.assignee.split(",")]

    tf = TMP_DIR / f"gh-create-issue-{int(time.time())}.json"
    with open(tf, "w") as f:
        json.dump(data, f)

    OWNER_REPO = get_owner_repo()
    cmd = ["gh", "api", f"repos/{OWNER_REPO}/issues", "--method", "POST", "--input", str(tf)]
    out, err, rc = run(cmd)
    clean_temp(tf)
    if rc != 0:
        print(f"[FAIL] Issue creation failed: {err}", file=sys.stderr)
        sys.exit(1)

    clean_temp(body_file)
    try:
        issue_data = json.loads(out)
        print(f"[OK] Issue created: {issue_data.get('html_url', '')}")
        print(f"       #{issue_data.get('number', '')} — {issue_data.get('title', '')}")
    except json.JSONDecodeError:
        print(out)


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

    clean_temp(body_file)
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
    fp.set_defaults(func=cmd_fetch_pr)
    
    fc = fetch_sub.add_parser("comments", help="Fetch PR comments and reviews")
    fc.add_argument("pr_or_url", help="PR number or URL")
    fc.add_argument("--output", type=str, default=None, help="Write formatted report to this file (default: reviews/remote/REVIEW_<branch>_fetched_<ts>.md)")
    fc.add_argument("--all", action="store_true", help="Include minimized/resolved comments (default: skip them)")
    fc.add_argument("--urls-only", action="store_true", help="Output JSON lines of filtered comment URLs only (for preflight consumption)")
    fc.set_defaults(func=cmd_fetch_comments)
    
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
    p.add_argument("gh_args", nargs=argparse.REMAINDER, help="Raw gh arguments (e.g., pr view 10)")
    p.set_defaults(func=cmd_cmd)

    # create pr
    p = sub.add_parser("create", help="Create a PR")
    p.add_argument("title", help="PR title")
    p.add_argument("body_file", help="Path to markdown file with PR body")
    p.add_argument("--head", type=str, default=None, help="Head branch (defaults to current branch)")
    p.add_argument("--base", type=str, default=None, help="Base branch (auto-detected if not specified)")
    p.add_argument("--draft", action="store_true", help="Create as draft")
    p.set_defaults(func=cmd_create_pr)

    # create issue
    p = sub.add_parser("create-issue", help="Create an issue")
    p.add_argument("title", help="Issue title")
    p.add_argument("body_file", help="Path to markdown file with issue body")
    p.add_argument("--label", type=str, default=None, help="Comma-separated labels to apply")
    p.add_argument("--assignee", type=str, default=None, help="Comma-separated assignees")
    p.set_defaults(func=cmd_create_issue)

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        parser.print_help()
        sys.exit(0)

    # If the first arg after script isn't a known command, show fallback message
    known = {"fetch", "post", "resolve", "minimize", "unminimize", "batch", "interact", "update", "create", "create-issue", "cmd", "fields"}
    if sys.argv[1] not in known:
        print(f"[INFO] 'gh.py {sys.argv[1]}' is not available yet. Use raw `gh` CLI directly:")
        print(f"       gh {' '.join(sys.argv[1:])}")
        print(f"[INFO] Run `uv run python .agents/scripts/gh.py --help` to see available commands.")
        sys.exit(0)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
