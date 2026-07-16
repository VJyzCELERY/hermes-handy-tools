# Agent Guide

This is a non-normative orientation page. Use `AGENTS.md` and `.agents/rules/` for policy, command files for exact command behavior, retained skills for reusable procedures, and templates for output structure.

## Common Work

Discover current public commands in the canonical `.agents/commands/README.md` inventory, then read the selected command file for exact inputs, preflights, outputs, and mutation behavior. Do not maintain another command catalog here.

Feature work starts from one open implementation issue and resumes from ignored `.agents/local/state/` through planning, test-first implementation, PR delivery, and baseline review. Command-owned artifacts remain in their documented locations, including `.agents/local/state/`, `reviews/`, `tmp/`, and `.worktrees/`.

Consumer clones publish planning revisions to one labelled Specs issue per implementation issue by default. This template repository uses the ignored `.agents/local/planning-profile.json` file containing `{"profile":"local"}` to retain local planning artifacts while developing the template itself; do not commit that profile.

## Minimal Code And Technical Debt

Implement only current requirements and prefer deletion, standard-library or native capabilities, existing dependencies, and finally the smallest new code. Do not leave production stubs silently.

Create a collision-checked stable ID with `/debt new`, then record the compromise and objective cleanup trigger using `[DEBT][DEBT-XXXXXXXX]: ... | trigger: ...` in the language's comment syntax. Use `/debt list` or `/debt check` for inventory and validation. When public tracking is useful, `/debt harvest DEBT-XXXXXXXX` searches open and closed issues first, then creates a confirmed issue only when none contains that ID. The source marker does not change; related markers may intentionally share the same ID and issue.

## Reusable Skills

Discover current skills from `.agents/skills/*/SKILL.md`; each file's frontmatter owns its name and description. Do not maintain a second skill catalog here.

For debugging, reproduce the smallest failure, inspect existing diagnostics, isolate the failing layer or test, fix the cause, and run the narrow check followed by the relevant full suite.
