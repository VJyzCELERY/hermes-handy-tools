---
description: Agent behavior and orchestration rules, core principles, project boundary
globs: "*.md, *.py"
alwaysApply: false
---

# Agent Behavior Rules

## Core Principles
- **Simplicity First**: Prefer simple solutions. If it feels complex, break it down.
- **Test-First**: Write failing tests before implementation. No exceptions.
- **Question the Spec**: Challenge assumptions during review — specs can be wrong.
- **No Overengineering**: Implement only what's in the spec. Avoid premature abstraction.

## Project Boundary
- Stay inside the project root. Use `./tmp/` for temp files (gitignored).
- Never use system `/tmp/` for project work.
