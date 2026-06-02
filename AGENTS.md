# Agents Documentation

This project uses the `.agents/` directory for all AI agent-related configuration, commands, templates, and documentation.

**Baseline harness is opencode, but all instructions are harness-agnostic.** If your harness does not support a specific mechanism (skill loading, tool detection, etc.), fall back to reading files directly and executing commands via bash.

---

## Normative Hierarchy

When instructions conflict, apply this precedence:

1. **`AGENTS.md`** — top-level operational contract (this file)
2. **`.agents/commands/`** — command definitions and contracts
3. **`.agents/skills/<name>/SKILL.md`** — tactical how-to guidance
4. **`.agents/rules/<name>.md`** — context-specific rules loaded by intent
5. **`.agents/templates/`** — document templates for generated output (specs, designs, PR body, reviews, etc.)
6. **`.github/ISSUE_TEMPLATE/`** — GitHub Issue Forms for human contributors (bug reports, feature requests, roadmaps)
7. **`.agents/docs/`** — reference documentation (guides, legacy content)

---

## Critical Rules

0. **Run start preflight** — At the start of every session, run `uv run python .agents/scripts/preflight-start.py`. This detects your OS and establishes the project boundary so you never operate outside it.
1. **Never leave the project root** — Your attached root directory is your entire world. Do NOT read, write, or execute anything outside it. If you need temporary files, use `./tmp/` (already gitignored) and clean up after yourself. Never use system `/tmp/`.
2. **Parent agents: instruct subagents to read AGENTS.md** — Whenever you delegate to a subagent, explicitly tell it to read this AGENTS.md file first. Subagents start with zero context and won't know these rules unless told.
3. **Ask when uncertain** — If any instruction is ambiguous or incomplete, use the question/ask tool to clarify (priority). Only write questions inline if your harness has no such tool. Do NOT guess. Subagents report questions to the parent orchestrator, not the user.
4. **Ask before committing** — Never commit or push without explicit user permission. Each batch needs a fresh ask unless the user grants unrestricted permission.
5. **Issue templates are in `.github/ISSUE_TEMPLATE/`** — Human-contributed bug reports, feature requests, and roadmaps use GitHub Issue Forms there. Agent-generated issue content (via gh.py) should reference these templates when creating structured issues.
6. **Load rules dynamically based on intent** — Before taking any action, load the relevant `.agents/rules/` files for what you're about to do. Rules are context-specific:
   - **Implementation/coding**: Load `002-code-standards.md` before writing any code
   - **Testing**: Load `003-testing.md` before writing tests
   - **Review**: Load `004-review-standards.md` before reviewing
   - **Architecture/planning**: Load `001-agent-behavior.md` and `005-project-structure.md`
   - **Commits/PRs**: Load `006-commits-and-prs.md` before committing or creating PRs
   - If exploring or asking questions, you don't need to load any rules yet — load them only when you're about to act.
7. **Implementation always starts with spec, design, tests** — If asked to implement something, you MUST:
   a. Ask clarifying questions first: what is the feature called? which subproject does it belong to? if the subproject doesn't exist yet, propose creating it.
   b. Create `spec.md` using `.agents/templates/spec.md`
   c. Create `design.md` using `.agents/templates/design.md`
   d. Write tests before code (test-first)
   e. Load coding standards before writing any source code
   f. Only then implement
   This applies regardless of whether the user explicitly mentioned specs or not — it's the default workflow.
8. **Use templates** — Before generating any document (PR body, spec, design, review, implementation plan, task list), check `.agents/templates/` first and follow the template structure. For PR bodies specifically, you MUST always use `.agents/templates/PR-body.md` — never write a PR body without filling in the template.
9. **Run preflight scripts** — Commands reference preflight scripts in `.agents/scripts/`. Run them before executing the command. If a preflight fails, read the script manually to recover.
10. **Use `uv run` for Python** — Never bare `python` or `pytest`. Always `cd <subproject-dir> && uv run`.
11. **Use gh.py for ALL PR operations** — All PR operations (read and write) MUST go through `.agents/scripts/gh.py`. This includes: creating PRs, fetching PR details/comments, posting reviews/comments, updating bodies/titles, resolving threads. Only use raw `gh` CLI when gh.py doesn't have the subcommand you need AND you've verified with `uv run python .agents/scripts/gh.py --help`. If gh.py fails with a syntax/transient error, retry once after a 2-second pause before falling back to raw `gh`.
12. **Review files are local-only** — Files under `./reviews/` are gitignored and must NEVER be committed or pushed. They are local artifacts for tracking findings during the review cycle. Subagents: if you generate a review file, do NOT `git add` or commit it.

---

## How to Explore `.agents/`

Everything you need is in `.agents/`. Explore it like a filesystem — only read what you need:

```
.agents/
├── commands/        # Slash command definitions (load on demand)
├── skills/          # How-to guides for each command/tool (load on demand)
├── rules/           # Context-specific rules loaded based on intent
├── tools/           # Custom tool definitions (opencode format, invoke scripts/)
├── scripts/         # Python scripts (gh.py, preflight-*.py)
├── templates/       # Document templates (check before generating)
└── reviews/         # Archived review reports

.github/ISSUE_TEMPLATE/   # GitHub Issue Forms (bug reports, features, roadmaps)
```

### When to load what

| Trigger | Load this |
|---------|-----------|
| Slash command received | `.agents/commands/<name>.md` + matching skill from `.agents/skills/<name>/` |
| Before any script | Run preflight first: `uv run python .agents/scripts/preflight-<name>.py` |
| Need PR/review help | Load skill: `gh` or read `.agents/skills/gh/SKILL.md` |
| Need git help | Load skill: `git` or read `.agents/skills/git/SKILL.md` |

### Dynamic rule loading

Rules live in `.agents/rules/` and are **loaded only when relevant** — not all at once:

| When you're about to... | Load these rules |
|------------------------|-----------------|
| Plan or design architecture | `001-agent-behavior.md`, `005-project-structure.md` |
| Write code | `002-code-standards.md` |
| Write tests | `003-testing.md` |
| Review code/docs/specs | `004-review-standards.md` |
| Commit or create a PR | `006-commits-and-prs.md` |

List available skills: `ls .agents/skills/` — each is a directory with a `SKILL.md` inside.

List available tools: run `uv run python .agents/scripts/gh.py --help`.

List available rules: `ls .agents/rules/`

### Common modules

Commands reference `_common-*.md` files for shared patterns. These are loaded on demand:

| Module | Load when |
|--------|-----------|
| `_common-preflight.md` | Running any review command |
| `_common-git-steps.md` | Needing branch/commit/diff info |
| `_common-review-steps.md` | Validating or verifying findings |
| `_common-closing-gate.md` | Finishing any command |

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `/begin-workflow` | Full pipeline: plan → implement → review → archive |
| `/begin-worktree` | Creates a new worktree + branch for feature development |
| `/plan` | Creates implementation plan + task list from spec & design |
| `/implement` | Executes plan tasks using TDD |
| `/review-loop` | Review cycle: report → validate → fix → fresh → archive |
| `/review-report` | Scoped code review of current branch changes |
| `/review-validate` | Full pipeline: clarify vague findings → verify statuses |
| `/review-clarify` | Improves review precision — rewrites vague findings |
| `/review-verify` | Checks each finding: addressed, invalid, or still OPEN |
| `/review-implement` | Applies fixes for review findings (does NOT update report) |
| `/review-post` | Posts review as a PR review with inline comments |
| `/review-update` | Follows up on PR review (resolve threads, flag remaining) |
| `/review-fetch` | Fetches unresolved PR comments into a review report |
| `/review-refresh` | Refreshes PR review state — fetches latest comments and updates local tracking |
| `/review-archive` | Logs completed cycle then archives the review report |
| `/rebase` | Safely rebases current branch onto target |
| `/commit-cleanup` | Cleans up commit history — squashes fixups, removes duplicates |
| `/worktree-prune` | Removes inactive worktrees (checks PR status) |
| `/worktree-cleanup` | Cleans up local artifacts in the current worktree |
| `/setup-project` | Bootstraps `.agents/` structure in a new project |

All commands reference preflight scripts in `.agents/scripts/`. Run the preflight first. If it fails, read the script's `<EOF_DESC>` section to understand what to fix.
