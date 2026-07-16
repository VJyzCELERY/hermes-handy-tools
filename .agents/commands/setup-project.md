---
description: Initializes or updates agent infrastructure inside this repository
subtask: true
---

# Setup Project

**Query**: `$1` must be `.`. **Source**: `$2` required template URL.

Read root `AGENTS.md`. Set `TEMPLATE_URL=$2` and stop if it is empty. Reject any target other than the current repository root. This command updates the current repository only; it cannot bootstrap a nested or different repository.

Preflight access to the canonical template wiki before updating:

```bash
uv run python .agents/scripts/setup_project_preflight.py
```

Preview through the version-driven updater, which clones only into the fixed
repository-local temporary directory `./tmp/setup-project-template`:

```bash
uv run python .agents/scripts/setup_project.py preview . "$TEMPLATE_URL"
```

The exact preview reports `current`, rejects downgrades, and classifies only
version upgrades. Preserve project-specific files, local reviews, `.agents/local/`,
and conflicting harness aliases. If the preview has no conflicts, confirm it
immediately before applying the prepared preview:

```bash
uv run python .agents/scripts/setup_project.py apply . --confirm
```

The updater applies only approved upstream changes, creates missing `.opencode`,
`.codex`, `.claude`, and `.hermes` relative aliases, writes the incoming marker
last, removes only `./tmp/setup-project-template`, and runs preflight.

## Required Context

- Root `AGENTS.md`; resolved root/target/source; `./tmp/`.

## Mutations

- Approved files and missing aliases at the current repository root; local clone under `./tmp/`. No Git-history or remote mutation.

## Confirmation

- Confirm the exact updater preview immediately before `apply . --confirm`.
  Outside-root targets, conflicts, and downgrades are rejected, not confirmable.

## Failure

- Stop on containment/symlink/source/clone/copy/preflight failure. Use only the fixed repository-local temporary path and never clean outside `./tmp/setup-project-template`.
