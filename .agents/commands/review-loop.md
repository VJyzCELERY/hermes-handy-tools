---
description: Review loop orchestrator — delegates each step to subagents with minimal interference
subtask: true
---

Run the review loop: review-report → review-validate → review-implement → review-verify → repeat until clean → review-archive.

> Load skill: review-loop (for loop orchestration guidance)

**Query**: $1 (— specify what to review, scope, focus, or any custom prompt for review-report, e.g., "review src/my-sdk for security issues" or "src/my-subproject/")

---

## Role: Review Orchestrator

You are the **review orchestrator**. Your job is to follow the loop below, delegating **each step to a fresh subagent**. You do not load skills, read AGENTS.md yourself, or specify review directories — the subagents handle all of that. Minimal interference.

### Bare Command Only — Critical Rule

When delegating to a subagent, send **only the raw command string** — nothing before, nothing after. No preamble, no instructions, no "your job is to...", no "specifically:". The subagent reads the command file and handles everything independently.

**✅ Correct:**
```
run @.agents/commands/review-report.md review PR docs readiness such as spec.md, design.md, task.md and implementation-plan.md
```

**❌ Wrong — do NOT add extra text:**
```
Please run the review-report command.
Your job is to follow the instructions in review-report.md...
Specifically:
1. First read...
2. Read AGENTS.md...
```

If the user provided **additional notes** that are relevant to a specific step, **append them naturally to the end of the bare command** — still no preamble:

```
run @.agents/commands/review-report.md <user_prompt> — also check that all new functions have docstrings
```

This applies to every step in the loop. The command is all the subagent needs.

Each subagent command follows this format (defaults shown — user may override any step):

| Step | Default Bare Command |
|------|---------------------|
| Review-Report | `run @.agents/commands/review-report.md <user_prompt>` or `run @.agents/commands/review-report.md <user_prompt> — <additional_note>` |
| Review-Validate | `run @.agents/commands/review-validate.md` |
| Review-Implement | `run @.agents/commands/review-implement.md` |
| Review-Verify | `run @.agents/commands/review-verify.md` |
| Review-Archive | `run @.agents/commands/review-archive.md` |

---

## Initial Questions

Ask the user for the review-report prompt first, then ask about each remaining step's command:

### 1. Review-Report Command

> "What should the review report scope/prompt be? (e.g., 'src/my-sdk' or 'review auth module for security')"

This is required and becomes the `<user_prompt>` for the review-report command.

### 2. Remaining Step Commands (default or custom)

For each remaining step, ask the user if they want the **default command** or a **custom one**. List the defaults:

| Step | Default Command |
|------|----------------|
| Review-Validate | `run @.agents/commands/review-validate.md` |
| Review-Implement | `run @.agents/commands/review-implement.md` |
| Review-Verify | `run @.agents/commands/review-verify.md` |
| Review-Archive | `run @.agents/commands/review-archive.md` |

> "For each step below, type 'default' to use the default shown above, or type your own custom command. Press enter to accept all defaults."

Collect the user's choice for each step individually. Record them — the orchestrator uses the chosen command for that step throughout the loop.

### 3. Additional Notes or Rules

> "Any additional notes or rules for the loop? (e.g., 'skip review-verify if only one finding', 'run tests after each implement') — leave blank if none."

Once answered, rest of the loop runs fully automated. The orchestrator uses the recorded commands and follows any additional notes.

---

## Instructions

Enter the loop and follow these steps in order:

### Step 1: Review Report (Subagent)

Send the review-report command the user provided (or the default `run @.agents/commands/review-report.md <user_prompt>`):

```
<user_chosen_review_report_command>
```

- If the review report returns **no OPEN issues** (clean) → proceed to **Step 6** (Archive).
- If the review report returns **OPEN issues** → proceed to **Step 2**.

### Step 2: Review Validate (Subagent)

Send the validate command the user chose (or the default):

```
<user_chosen_validate_command>
```

### Step 3: Review Implement (Subagent) + Commit

Send the implement command the user chose (or the default):

```
<user_chosen_implement_command>
```

After the subagent finishes, the orchestrator **commits the changes** locally:

```bash
git add -A && git commit -m "review: apply fixes from review cycle"
```

> **Important**: Do NOT push. This is a local commit only.

> **Early push optimization**: If the review report agent keeps flagging "unpushed commits" as an issue across cycles, the orchestrator may **squash all unpushed commits into one and push early** after this step (does NOT terminate the loop). See Step 7 for squash+push approach.

Proceed to **Step 4**.

### Step 4: Review Verify (Subagent)

Send the verify command the user chose (or the default):

```
<user_chosen_verify_command>
```

- If **all issues are ADDRESSED** → immediately run **Review Archive** (inline, not Step 6), then proceed to **Step 5** → Step 1 (fresh review).
- If **issues are still OPEN** → go back to **Step 3** (Implement again).

> **Archive after verify**: When verify confirms all issues are addressed, archive the current cycle before the fresh review. This preserves the cycle's findings for traceability.

To archive inline, send the archive command the user chose for this step:

```
<user_chosen_archive_command>
```

### Step 5: Goto Step 1

After archive completes, go back to **Step 1** for a fresh review report to check if fixes introduced new issues.

### Step 6: Review Archive (Subagent)

Only reached when Step 1 returns a clean report (no OPEN issues) on the **first cycle** (no fixes were needed).

Send the archive command the user chose (or the default):

```
<user_chosen_archive_command>
```

Proceed to **Step 7**.

### Step 7: Squash Unpushed Commits → Push → Terminate

Check for unpushed local commits:

```bash
git log @{u}..HEAD --oneline
```

If there are unpushed commits:
1. **Squash** all unpushed commits into a single commit using `git reset --soft @{u}` + `git commit`
2. **Push** with a normal `git push` (no force push)

> **Critical rule**: This must NOT require `--force` or `--force-with-lease`. If a force push would be needed, the agent is doing something wrong. In that case, do NOT push — abort and report the situation.

Once push succeeds, the review loop is complete and terminates.

> **Note on early push**: If the review report repeatedly flags "unpushed commits" as an issue, the orchestrator may apply this squash+push early (after Step 3) without terminating the loop. This silences the false-positive review finding so the loop can continue cleanly.

---

## Loop Flow Diagram

```
Step 1: Review Report
  ├── Has OPEN issues → Step 2
  └── No issues (clean) → Step 6 (Archive) → Step 7

Step 2: Review Validate → Step 3

Step 3: Review Implement → git commit (NO PUSH) → Step 4
  └── (Early squash+push if review report flags unpushed commits)

Step 4: Review Verify
  ├── All ADDRESSED → Archive → Step 5 → Step 1 (fresh review)
  └── Still OPEN → Step 3 (fix again)

Step 5: Goto Step 1

Step 6: Review Archive (initial clean only) → Step 7

Step 7: Squash unpushed commits → Push → Terminate
```

---

## Required Context

- Preflight: none (subagents handle their own preflights)
- Skills: none (subagents load their own skills)
- Rules: none (subagents load their own rules)
- Templates: none
- Mutates files: yes (orchestrator commits after review-implement)
- Mutates git history: yes (orchestrator commits and squashes)
- Mutates remote: yes (orchestrator pushes at Step 7 or early push)
- Requires user confirmation: yes (review-report prompt + step commands + additional notes)

## Important

- **Bare command only**: Send the raw `run @.agents/commands/review-<step>.md ...` string — nothing else. No preamble, no extra instructions. The subagent reads the command file and handles everything.
- **Additional notes**: If the user provided notes, the orchestrator follows them. Append relevant notes to the bare command when they affect a subagent's task.
- Delegate **each step** to a **fresh subagent** — never do the work yourself.
- Wait for each subagent to complete before proceeding.
- Do **not** instruct subagents to read AGENTS.md — they handle that themselves.
- Do **not** specify review directories — subagents determine paths independently.
- Do **not** load skills for the review steps — subagents load their own.
- The initial questions are the **only** user interaction — the loop runs fully automated after that.
- The review-report prompt is entirely user-determined — pass it verbatim to the subagent.
- **After Step 3** (review-implement): orchestrator always commits the changes locally. Do NOT push.
- **Archive after verify**: When Step 4 (verify) confirms all ADDRESSED, run archive immediately — do NOT skip to Step 1 first. The archive preserves the cycle before the fresh review.
- **Step 6** is only for the **initial clean report** path (no issues found on first review).
- **Step 7**: Squash ALL unpushed commits into a single commit, then push normally. Must NOT require `--force`.
- **Early push optimization**: If the review report keeps flagging "unpushed commits" as an issue, squash+push early after the next Step 3 commit. This does NOT terminate the loop — the loop continues normally.
- If a squash+push would require force push, the agent is doing it wrong — abort and report.
