---
name: plan
description: Create implementation plans and task lists from spec and design documents
license: MIT
compatibility: opencode
metadata:
  type: command-skill
  source: .agents/commands/plan.md
---

# Skill: plan — Create Implementation Plan from Spec

## Purpose

Read a spec and design document, then create an implementation plan and task list with concrete steps.

## Prerequisites

- `spec.md` and `design.md` exist in the target feature directory

## Execution

1. Read `spec.md` and `design.md`
2. Read template: `.agents/templates/implementation-plan.md` and `.agents/templates/task.md`
3. Break down into phases, then tasks with clear acceptance criteria
4. Write `implementation-plan.md` and `task.md` in the target directory

## Common Pitfalls

- Tasks must be small enough to complete in one pass (each task is one TDD cycle)
- Include test requirements in each task
- Reference relevant rules from `.agents/rules/`
