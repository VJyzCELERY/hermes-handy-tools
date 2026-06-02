---
name: implement
description: Execute implementation plan tasks using strict TDD
license: MIT
compatibility: opencode
metadata:
  type: command-skill
  source: .agents/commands/implement.md
---

# Skill: implement — Execute Plan Tasks Using TDD

## Purpose

Implement code changes following an existing implementation plan and task list (created by `/plan`). Uses strict TDD: write failing test first, then make it pass.

## Prerequisites

- `implementation-plan.md` and `task.md` exist in the target directory

## Execution

1. Read the plan and task list
2. For each task: write failing test → implement → verify test passes → refactor → mark task complete
3. Always use `uv run` for Python/pytest commands
4. Update `task.md` as tasks are completed

## Common Pitfalls

- Do NOT implement more than the plan specifies
- Read relevant rules from `.agents/rules/` first
- Only modify files in scope of the task
- Run tests after each task before marking complete
