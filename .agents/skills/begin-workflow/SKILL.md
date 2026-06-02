---
name: begin-workflow
description: Automate the complete specs implementation process using subagents for each phase
license: MIT
compatibility: opencode
metadata:
  type: command-skill
  source: .agents/commands/begin-workflow.md
---

# Skill: begin-workflow — Full Spec-to-Cleanup Automation

## Purpose

Orchestrate the complete feature workflow: planning → implementation → review loop → cleanup. You are the workflow-orchestrator; delegate each phase to a fresh subagent.

## Prerequisites

- spec.md and design.md exist for the feature (or user opts to create them)
- Current branch is not `main` (or user confirmed working on main)

## Execution

1. Read `.agents/commands/begin-workflow.md` for the full workflow
2. Ask user clarifying questions (tighten scope, PR creation, etc.)
3. Delegate `/plan` → wait → verify plan files exist
4. Delegate `/implement` → wait → verify tasks complete
5. Optionally create PR via `gh.py create`
6. Enter review loop: `/review-report` → `/review-validate` → `/review-implement` → repeat until clean → `/review-archive`
7. Each loop iteration uses a fresh subagent with zero prior context

## Common Pitfalls

- Do NOT fix code yourself — always delegate to subagents
- Do NOT pass context between subagents — fresh each time
- At least 4 full-scope cycles before tightening scope
- After validation returns clean, ALWAYS run one more fresh review
