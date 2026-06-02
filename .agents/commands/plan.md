---
description: Creates implementation-plan.md and task.md from spec.md and design.md
subtask: true
---

Create an implementation plan from existing spec.md and design.md files.

> Load skill: plan (for implementation planning)

**Query**: $1 (natural language query — specify the feature or directory, e.g., "plan the auth feature in specs/user-auth/" or simply "specs/my-feature/")
**Additional Context (Optional)**: $2 (any additional context or priorities to consider)


1. **Locate spec.md**: Search for spec.md in `$1` or its subdirectories
2. **Locate design.md**: Find design.md in the same directory as spec.md
3. **Read and Analyze**: Read both files to understand the requirements and design
4. **Apply Additional Context**: If $2 is provided, incorporate that into the plan
5. **Create implementation-plan.md**: Generate a detailed implementation plan in the same directory as spec.md with:
   - Context (priority, effort, dependencies)
   - **Success Criteria — Integration Tests (TDD first)**: Define the integration tests that prove the feature works. Include **code snippets** for each test scenario. Tests are written FIRST — implementation is only complete when they pass.
   - Verification Plan
   - Proposed Changes (with NEW/MODIFY/DELETE actions)
   - Architecture Changes
   - Dependencies
   - Risks and Mitigations
6. **Create task.md**: Generate a task checklist with these phases:
   - TDD Phase (tests first — write integration tests, run RED)
   - Implementation Phase
   - Testing Phase (run GREEN, unit tests, full suite)
   - Verification Phase
   - Documentation Phase
   - Review and Merge
7. **Use Task IDs**: Add `<!-- id: N -->` tags to each task for tracking

## Required Context

- Preflight: none
- Skills: plan
- Rules: 001-agent-behavior.md, 005-project-structure.md
- Templates: implementation-plan.md, task.md
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: no

## Important
- **Check templates first**: Read `.agents/templates/implementation-plan.md` and `.agents/templates/task.md` before generating — follow their structure
- Do NOT make any code changes — only create planning documents
- Output files must be in the same directory as spec.md
- Make the implementation plan detailed and actionable

Begin by locating spec.md and design.md, then create the implementation plan and tasks.