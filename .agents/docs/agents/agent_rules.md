# Agent Rules

This document defines the core principles and general rules for AI agents working in any project built from this template.

---

## Core Principles

### 1. Simplicity First

If the solution feels complex, it is. Break it down.

- Prefer simple solutions over clever ones
- Inline single-use helpers instead of extracting them
- Avoid premature abstraction
- Question every layer of indirection
- If you can't explain it simply, it's too complex

### 2. Test-First

Write failing tests before implementation. No exceptions.

- Unit tests must exist for all new logic
- Integration tests for workflows and APIs
- Tests validate the spec, not just the code
- Coverage is a side effect, not the goal

### 3. Question the Spec

During review, challenge assumptions. Specs can be wrong.

- Does the spec make sense?
- Are there gaps or contradictions?
- Is the proposed solution minimal?
- Flag spec issues early — do not blindly implement

### 4. No Overengineering

Flag unnecessary complexity, premature optimization, and gold-plating.

- Implement only what is in the spec
- Avoid "flexibility" that is not needed yet
- Simple code is maintainable code
- Do not add features not requested

---

## Project Boundary

- **Stay Inside the Project Root**: Your attached root directory is your entire world. Do NOT read, write, or execute anything outside it. The preflight-start.py script establishes this boundary at session start.
- **Use `./tmp/` for Temp Files**: If you need temporary files, create them in `./tmp/` (already gitignored) and clean up after yourself. Never use system `/tmp/`.
- **Boundary Check**: If you are ever uncertain whether a path is inside the project root, resolve it explicitly before proceeding.

---

## General Agent Rules

- **Responsible Use**: AI agents must be used to assist, not replace, developer judgment.
- **Ask Before Committing**: Agents must NEVER commit or push without explicit user permission.
  - After a batch of changes, ask: "Commit and push these changes?"
  - If permitted, commit and push.
  - A new batch in the same session requires a new ask — prior permission does not carry forward.
  - Exception: If the user explicitly grants unrestricted commit+push permissions (e.g., "always commit and push after our changes"), you may proceed without asking each time.
  - If unsure whether permission is ongoing, ask: "Do you want unrestricted commit+push permissions for this session?"
- **Document AI Contributions**: Indicate AI-assisted code in commit messages (e.g., `feat(scope): description [ai]`) or via inline comments (`# AI-generated`).
- **Ask When Uncertain**: If any instruction is ambiguous, incomplete, or conflicting, the agent MUST ask for clarification. Priority: use the native question/ask tool. Fallback: write questions inline if your harness has no such tool. Do NOT guess, assume, or proceed with partial information.
- **Subagent Exception**: Subagents MUST NOT ask the user directly. If a subagent has a question, it MUST report it to the parent orchestrator agent, which will decide whether to ask the user or resolve it internally.
- **Task Scoping**: Define specific, bounded tasks for AI agents. Avoid open-ended instructions.
- **Review All Output**: All AI-generated code must be reviewed by a human before merging.
- **Follow Project Standards**: AI agents must produce code that passes `make lint`, `make test`, and `make complexity` (run from the subproject directory: `cd src/<subproject> && make lint`) before output is considered complete.
- **Documentation Alongside Code**: AI agents must produce or update documentation (docstrings, README, guides, API docs) with the same priority as code changes. A feature is not complete until its docs are updated.
- **No Secrets in Output**: AI must never generate code that contains hardcoded secrets, credentials, or API keys.
- **Spec-Driven Development**: Before implementing any feature, ensure a spec.md and design.md exist. If the user asks for new work without specs, prompt them to create specs first. Use `.agents/templates/spec.md` and `.agents/templates/design.md`.
- **Use gh.py for PR Operations**: All PR/review write operations (posting reviews, comments, replies, resolving, updating PR body, creating PRs) must go through `.agents/scripts/gh.py`. Never use raw `gh pr edit`, `gh pr review`, or similar direct `gh` commands for PR write operations. Run `uv run python .agents/scripts/gh.py --help` to see available subcommands.
- **Worktree Enforcement on Main**: If the current branch is `main` and the user requests new feature work, the agent MUST:
  1. Ask for a branch name before proceeding
  2. Offer to create a worktree via `/begin-worktree <branch-name>`
  3. Allow bypass — this is a soft enforcement, the user can decline
  4. Only skip if user explicitly confirms they want to work directly on `main`

---

## Agent Behavior During Code Generation

- Read the relevant spec file before generating code
- Generate the minimum code that satisfies the spec
- Include docstrings for all functions and classes
- Include corresponding tests alongside generated code
- Follow naming conventions in `.agents/docs/project_rules/naming_conventions.md`
- Follow coding standards in `.agents/docs/project_rules/coding_standards.md`

---

## References

- `.agents/docs/agents/workflow.md` — development commands and commit guidelines
- `.agents/docs/agents/style.md` — code style enforcement rules
- `.agents/docs/agents/testing.md` — test organization and naming
- `.agents/docs/agents/code_review.md` — review standards and severity levels
- `.agents/docs/project_rules/coding_standards.md` — full coding standards
- `.agents/docs/project_rules/cognitive_complexity.md` — complexity limits
- `.agents/docs/project_rules/worktree.md` — worktree creation and management
