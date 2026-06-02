---
name: setup-project
description: Bootstrap or update .agents/ structure from MAIN-PROJECT-TEMPLATE
license: MIT
compatibility: opencode
metadata:
  type: command-skill
  source: .agents/commands/setup-project.md
---

# Skill: setup-project — Bootstrap or Update .agents/ Structure

## Purpose

Initialize a new `.agents/` directory in a project, or update an existing one with the latest template improvements.

## Execution

1. Determine template source: GitHub URL or local copy of MAIN-PROJECT-TEMPLATE
2. Clone/fetch the template
3. Copy `.agents/` structure to target project
4. Update root files if needed (AGENTS.md, PROJECT-GUIDELINES.md, pyproject.toml, .gitignore)
5. Verify `uv run python .agents/scripts/preflight-start.py` works

## Common Pitfalls

- Do NOT overwrite project-specific customizations in existing `.agents/`
- Use soft update mode for existing projects (compare by similarity, preserve customizations)
- Only update template-sourced files, preserve project-specific additions
