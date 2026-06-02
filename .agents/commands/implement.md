---
description: Executes implementation plan using TDD workflow
subtask: true
---

Execute an implementation plan from implementation-plan.md and task.md.

> Load skill: implement (for TDD implementation)

**Query**: $1 (natural language query — specify the feature or directory to implement, e.g., "implement the auth feature from specs/user-auth/" or simply "specs/my-feature/")
**Focus/Priority (Optional)**: $2 (e.g., "speed", "quality", specific feature to prioritize)


1. **Locate implementation files**: Find implementation-plan.md and task.md in `$1`
2. **Read implementation-plan.md**: Understand the proposed changes and architecture
3. **Read task.md**: Review the task checklist
4. **Apply Focus**: If $2 is provided, prioritize that focus area in implementation
5. **Execute Tasks**: Implement each task in order, following TDD workflow:
   - Write tests first (RED)
   - Implement code to pass tests (GREEN)
   - Refactor if needed
   - Run tests to verify
6. **Update Progress**: Update task.md as tasks are completed (use `[x]` for completed, `[ ]` for pending)
7. **Report Status**: Report progress against the task checklist

## TDD Workflow
- **RED**: Write failing tests first
- **GREEN**: Write minimal code to pass tests
- **REFACTOR**: Improve code quality while keeping tests green

## Constraints
- Do NOT modify implementation-plan.md - it serves as the source of truth
- Only update task.md to track progress
- Follow existing codebase conventions

## Available Commands
- Use `/review-report <directory>` to review your implementation
- Use `/review-validate <review-file>` to validate review findings
- Use `/review-implement <review-file>` to implement fixes

## Required Context

- Preflight: preflight-start.py
- Skills: implement
- Rules: 002-code-standards.md, 003-testing.md
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: no

Begin by reading the implementation-plan.md and task.md, then start executing tasks in order.