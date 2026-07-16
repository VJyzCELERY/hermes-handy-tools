# Common GitHub Ownership

Resolve the authenticated GitHub login through `gh.py`; never infer identity from Git configuration, issue authorship, or PR authorship. Claiming means adding that login to an issue and PR; preserve existing assignees:

```bash
uv run python .agents/scripts/gh.py claim <issue-or-pr-number> --format json
```

Fetch canonical issue and PR JSON before a claim. Preview the exact login and issue/PR numbers, then request confirmation immediately before the remote write batch unless `--auto` or inherited `/goal` authorization applies. Claim every selected issue before implementation and every resolved or created PR. Repeated claims are idempotent. Stop before implementation or delivery if identity lookup, context fetch, assignment, or verification fails.

New issues and PRs created through `gh.py` include the authenticated GitHub login automatically. New PRs are always drafts. Metadata updates preserve an existing PR's draft or ready state; readiness changes belong to an explicit later workflow.
