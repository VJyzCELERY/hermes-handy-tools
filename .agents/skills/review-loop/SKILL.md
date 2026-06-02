---
name: review-loop
description: Review loop orchestration — flow, edge cases, and orchestrator behavior
license: MIT
compatibility: opencode
metadata:
  type: command-skill
---

# Skill: review-loop — Orchestrate the Review Loop

## Purpose

This skill guides the **review orchestrator** through the review loop lifecycle: delegate each step to a fresh subagent via bare commands, commit fixes, handle unpushed commits, and terminate cleanly. The orchestrator does minimal work — subagents handle everything.

## Prerequisites

- User provides the review-report prompt/scope
- User may optionally provide additional notes or rules for the orchestrator to follow
- Subagents handle their own preflights, skills, rules, and AGENTS.md reading

## Loop Execution

The loop runs in this order:

```
Step 1: Review Report → OPEN? → Step 2 : Clean? → Step 6 (Archive) → Step 7
Step 2: Review Validate → Step 3
Step 3: Review Implement + commit (NO PUSH) → Step 4
Step 4: Review Verify → ADDRESSED? → Archive → Step 5 → Step 1 : OPEN? → Step 3
Step 5: Goto Step 1
Step 6: Review Archive (initial clean only) → Step 7
Step 7: Squash unpushed commits → Push → Terminate
```

### Default Commands Per Step

These are the default commands the orchestrator sends to subagents. Each step uses a bare command string — nothing else.

| Step | Default Bare Command | Description |
|------|-------------------|-------------|
| Review-Report | `run @.agents/commands/review-report.md <user_prompt>` | Scoped review of branch diff, generates report |
| Review-Validate | `run @.agents/commands/review-validate.md` | Clarify vague findings, then verify each one |
| Review-Implement | `run @.agents/commands/review-implement.md` | Apply code fixes from OPEN findings |
| Review-Verify | `run @.agents/commands/review-verify.md` | Check each finding: addressed, invalid, or still OPEN |
| Review-Archive | `run @.agents/commands/review-archive.md` | Log completed cycle, archive the report |

The orchestrator asks the user for each step before starting. The user may accept the default or provide a custom command (e.g., adding a focus flag or additional parameter).

### Orchestrator Rules

1. **Bare command only** — send the raw `run @.agents/commands/review-<step>.md ...` string. No preamble, no extra instructions.
2. **Fresh subagent per step** — never reuse a subagent across steps.
3. **No skill loading** — the orchestrator does not load skills. Subagents load their own.
4. **No AGENTS.md instruction** — do not tell subagents to read AGENTS.md. They handle that.
5. **No review directory** — do not specify review file paths. Subagents determine paths.
6. **Commit after implement** — after review-implement subagent finishes, the orchestrator runs `git add -A && git commit -m "review: apply fixes from review cycle"`. Do NOT push.
7. **Squash + push at termination** — at Step 7, squash all unpushed commits into one (`git reset --soft @{u}` + `git commit`) and push normally. Must NOT require `--force`.

### Custom Commands per Step

If the user provides a custom command for a step, the orchestrator uses that instead of the default. Custom commands still follow the bare command rule — just the string, no preamble.

**Examples of custom commands:**
```
run @.agents/commands/review-report.md src/my-sdk — focus on security only
run @.agents/commands/review-validate.md — only CRITICAL findings
run @.agents/commands/review-implement.md — fix all OPEN issues
run @.agents/commands/review-verify.md — re-check ISSUE-001 and ISSUE-002
run @.agents/commands/review-archive.md
```

### Additional Notes from User

If the user provides additional notes or rules beyond the step commands, the orchestrator should follow them. These may affect:
- **How the loop flows** (e.g., skip certain steps, repeat more times)
- **What the review-report subagent receives** (if the note modifies the scope/prompt)
- **What the review-implement subagent should focus on**
- **Post-commit behavior** (e.g., run tests after each implement)

Pass relevant notes to subagents by **appending them to the bare command string** in a natural way, e.g.:

```
run @.agents/commands/review-report.md <user_prompt> — also check that all new functions have docstrings
```

## Common Pitfalls

- **Orchestrator adds preamble**: Sending "Please run..." or "Your job is to..." before the command. The subagent reads the command file — it doesn't need extra context from the orchestrator.
- **Orchestrator tries to fix code**: Never fix code yourself. Delegate to `review-implement`.
- **Force push**: If squash+push at Step 7 requires `--force`, the agent is doing something wrong (e.g., the remote has commits the local doesn't know about). Abort and report.
- **Skipping the commit**: After `review-implement`, always commit. Forgetting means fixes are lost on next checkout.
- **Not asking for additional notes**: Always give the user the option to provide extra context before the loop starts.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Review report is clean (no OPEN issues) | Skip validate/implement/verify. Go directly to Step 6 (Archive) → Step 7. |
| Verify finds ALL ADDRESSED | Archive the cycle immediately, then go to Step 5 → Step 1 for fresh review. |
| Verify finds some ADDRESSED, some OPEN | Only the OPEN ones go back to Step 3. No archive — the cycle is not complete. |
| Review report flags unpushed commits repeatedly | Use early push optimization: squash+push after next Step 3 commit (does NOT terminate loop). |
| Force push would be required at Step 7 | Do NOT push. Abort and report — something is wrong with the branch state. |
| No unpushed commits at Step 7 | Skip squash+push. Just terminate. |
| User provides no additional notes | Run the loop normally with no modifications. |
