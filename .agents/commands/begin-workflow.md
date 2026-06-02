---
description: Automates the complete specs implementation process using subagents for each phase
subtask: true
---

Automate the complete specs implementation process: planning → implementation → review loop → cleanup.

> Load skill: begin-workflow (for full pipeline orchestration)

**Query**: $1 (natural language instruction describing what to build or which feature to implement — e.g., "implement user authentication for the SDK" or "build specs/my-feature/")
**Additional Context (Optional)**: $2 (any additional context or priorities)


## Initial Questions

**Use the question/ask tool to ask these (priority). Only write inline if your harness has no such tool.**

1. **Specs/Design**: "Do you have spec.md and design.md ready, or should I create them?" If not, use `.agents/templates/spec.md` and `.agents/templates/design.md`.
2. **Branch/PR**: If no PR exists for the current branch: "Do you want me to create a PR after implementation, or skip PR creation?" If yes, the PR is created after Phase 2 (implement) completes, before entering the review loop.
3. **Scope tightening**: "Do you want to tighten the review scope as iterations progress, or keep every cycle fresh?" Default is tighten if not specified.
4. **Any other clarifications**: If the query is ambiguous, ask for specifics.

Once answered, the entire workflow runs fully automated — the orchestrator delegates to fresh subagents for each phase without further user input.

---

## Workflow-Orchestrator Role

The agent that executes this command is the **workflow-orchestrator**. You (the running agent) are the workflow-orchestrator — you delegate to **fresh subagents** for every single step. You own the loop, apply oversight rules, and make go/no-go decisions.

### Critical Rule: Every Step Uses a Fresh Subagent with Clean Context

**Every step in this workflow uses a dedicated subagent that starts with zero context from any prior step.** Subagents are intentionally kept free of prior context to ensure fresh perspectives. This applies to:

- `/plan` → Subagent 1
- `/implement` → Subagent 2
- `/review-report` → Subagent 3, 6, 9, ...
- `/review-validate` → Subagent 4, 7, 10, ...
- `/review-implement` → Subagent 5, 8, 11, ...
- `/review-archive` → Subagent N

Each subagent is a clean, independent invocation. Do NOT pass prior findings, fix history, or any context between them. The workflow-orchestrator alone maintains the bookkeeping.

---

## Overview

```
Planning (Subagent 1) → Implementation (Subagent 2) → Review Loop → Cleanup

Review Loop:
  Review-report (Subagent 3)
       ↓
  Review-validate (Subagent 4) → If OPEN: Review-implement (Subagent 5) → Review-validate (Subagent 6) → repeat
       ↓
   If CLEAN → Fresh Review-report (Subagent 7) ← independent, zero prior context
        ↓
   If NEW ISSUES → Return to Validate
   If CLEAN (zero issues) → Exit Loop → Review-archive (Subagent N)
```

---

## Important Global Rule: Use `uv run` for Python

All subagents MUST `cd <subproject-dir> && uv run` for Python/pytest commands.
Bare `python` or `pytest` may import from the wrong worktree.

---

## Instructions

### Phase 1: Planning (Subagent 1)

Delegate to a fresh subagent:

> Run /plan for $1

Wait for the subagent to complete and verify implementation-plan.md and task.md are created.

### Phase 2: Implementation (Subagent 2)

Delegate to a fresh subagent:

> Run /implement for $1

Wait for the subagent to complete and verify tasks are marked complete in task.md.

### Phase 2.5: Create PR (if opted in)

If the user opted for PR creation during initial questions, push the branch and create a PR:

```bash
git push origin <branch>
uv run python .agents/scripts/gh.py create "type(scope): title" ./tmp/pr-body.md
```

The base branch is auto-detected — `gh.py` checks if a PR already exists for this branch (uses that base), or determines the logical parent branch. Use `.agents/templates/PR-body.md` for the PR body.

### Phase 3: Review Loop

Enter a loop that continues until truly clean (no issues found in a FRESH review):

**Step 1: Review-report (Subagent 3)**

Delegate to a fresh subagent:

> Run /review-report for $1 with focus on code quality and spec compliance — read the PR body and title first, adjust scope accordingly, and check PR body/title compliance against specs

**Step 2: Review-validate (Subagent 4)**

Delegate — review file is always at `./reviews/REVIEW_{name}.md`:

> Run /review-validate for ./reviews/REVIEW_{name}.md

**Step 3: If OPEN issues exist → Review-implement (Subagent 5)**

Delegate:

> Run /review-implement for ./reviews/REVIEW_{name}.md

After fixing, return to Step 2 for re-validation (this uses a NEW subagent — Subagent 6, then 8, then 10, etc.).

**Step 4: If VALIDATE returns CLEAN (no OPEN issues) → Run FRESH Review-report (Subagent N)**

This MUST be a fresh, independent review. Do NOT give the subagent any context about previous reviews or findings:

> Run /review-report for $1 - perform a FRESH independent review. Do NOT use any context from previous reviews. Treat this as a brand new review and check for any remaining issues from scratch — also read the PR body and title, adjust scope, and check PR body/title compliance

**Step 5: Check Fresh Review Result**
- If fresh review has ANY new issues → return to Step 2 (Validate → Implement → Validate → Fresh Review)
- If fresh review returns CLEAN (zero issues) → Exit Review Loop and proceed to Cleanup

### Phase 4: Review-archive (Subagent N)

Delegate to a fresh subagent:

> Run /review-archive for ./reviews/REVIEW_{name}.md

---

## Workflow Summary (Subagent Sequence)

```
Subagent 1:  /plan
Subagent 2:  /implement
  ── Review Loop ──
Subagent 3:  /review-report                               (initial review)
Subagent 4:  /review-validate                             (validate findings)
Subagent 5:  /review-implement                            (fix open issues)
Subagent 6:  /review-validate                             (re-validate after fix)
             ...repeat 4-6 as needed...
Subagent N:  /review-report                               (fresh, independent review)
             if issues → back to Subagent N+1 (validate)
             if clean → proceed to cleanup
Subagent N:  /review-archive                              (log + archive review)
```

---

## Review Loop Oversight Rules (Workflow-Orchestrator Responsibilities)

The **workflow-orchestrator** (you) owns the loop and must apply these rules. The subagents are intentionally kept free of prior context to ensure fresh perspectives.

### 1. Bookkeep Review History

Maintain a running ledger of every finding across all cycles. For each new fresh review:

1. **Check each finding against the ledger**: has this exact issue been raised and addressed before?
2. **If yes → Invalidate**: mark it INVALID with a note: "Already addressed in cycle N — no regression detected."
3. **If no → Keep as OPEN**: the finding is genuinely new.

**Do NOT invalidate simply because a finding looks similar or overlaps.** Only invalidate if the exact same issue (same file, same line, same description) was previously addressed.

### 2. Handle Reopened Issues

A previously addressed finding may legitimately reopen:
- If **code has changed** since the fix (the fix was reverted or modified), treat as a valid new OPEN finding.
- If **code has NOT changed** since the fix, the reviewer is wrong — **invalidate**.
- Verification: `git diff <commit-where-fix-was-applied> -- <file>` to check for regressions.

### 3. Tighten Scope as Issues Shrink

As the loop progresses and findings become increasingly nitpicky, the orchestrator should tighten review scope **conservatively** — bias toward keeping scope wide:

- **First 4 cycles**: Full scope — all spec compliance, code quality, test coverage.
- **Cycles 5-8**: Narrow to spec compliance and correctness issues. Defer cosmetic/style suggestions.
- **Cycles 9+**: Only accept findings that represent **real bugs**, **spec violations**, or **test gaps that would let actual bugs through**.

### 4. Workflow-Orchestrator Validation Gate

After each fresh review, before passing findings to the validate-fix pipeline:

1. Run each finding through the ledger (rule 1).
2. Check for reopened issues with code diff verification (rule 2).
3. Assess severity against current cycle scope (rule 3).
4. **Pass all remaining findings through** — do NOT proactively filter or dismiss. Let `review-validate` and `review-verify` make the final determination. The orchestrator only removes true duplicates (exact same finding from prior cycle) and out-of-scope items (findings about code not in the diff).

---

## Important

- The **workflow-orchestrator** (you) is responsible for applying the Review Loop Oversight Rules. Do NOT pass oversight context to subagents.
- Delegate each phase to a fresh subagent.
- **Do NOT fix code yourself** — always delegate implementation to subagents via review-implement. The orchestrator owns the loop, not the code.
- Wait for each subagent to complete before proceeding.
- After validation returns clean, ALWAYS run one more fresh review.
- For FRESH review: explicitly tell subagent to be independent with no prior context.
- The orchestrator filters and gates fresh review findings through the oversight rules before passing to validate.
- Stay scoped to the spec — don't implement or review things outside the scope.
- Run actual commands and tests — don't assume results.
- Always instruct subagents to read this AGENTS.md file first — they start with zero context and won't know the rules otherwise.
- Always instruct subagents to load the relevant skill (e.g., `gh`, `preflight`) before running tools — list available skills with `ls .agents/skills/` if unsure.
- Always instruct subagents to `cd <subproject-dir> && uv run` for Python/pytest.
- Always instruct subagents to read the relevant rules from `.agents/rules/` first, then check `.agents/templates/` before generating documents — rules define conventions, templates define structure.
- When delegating review-report, instruct the subagent to read the PR body and title to understand scope and check PR body/title compliance against specs.
- All review files live at `./reviews/REVIEW_{name}.md` — they are gitignored and must NEVER be committed or pushed.

## Required Context

- Preflight: preflight-start.py
- Skills: begin-workflow
- Rules: 001-agent-behavior.md, 002-code-standards.md, 003-testing.md, 005-project-structure.md
- Templates: spec.md, design.md, implementation-plan.md, task.md, PR-body.md
- Mutates files: yes
- Mutates git history: yes
- Mutates remote: yes
- Requires user confirmation: yes (initial questions on scope, PR creation, tightening)

Begin by starting Subagent 1 for the planning phase.
