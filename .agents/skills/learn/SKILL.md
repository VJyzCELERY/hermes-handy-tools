---
name: self-learning
description: Guide for creating and updating project-specific agent skills
license: MIT
compatibility: opencode
metadata:
  type: workflow
---

# Skill: Self-Learning — Creating and Updating Project-Specific Skills

## Purpose

As agents work on a project, they will encounter recurring patterns, conventions, and workflows that are not yet documented. This skill enables agents to **create new skills** and **update existing skills** to capture these patterns, making future tasks more efficient and consistent.

## When to Create a Skill

Create a new skill (`.agents/skills/<name>/SKILL.md`) when you notice:

1. **Recurring operations** — the same multi-step process is done 3+ times
2. **Project-specific gotchas** — a tool or API behaves differently than expected
3. **Complex workflows** — a sequence of commands that is error-prone if done manually
4. **New tool integrations** — the project adopts a new tool or service
5. **Common mistakes** — patterns that repeatedly cause issues during reviews

## Skill Structure

Each skill lives in its own directory under `.agents/skills/<name>/SKILL.md`:

```
.agents/skills/
├── <skill-name>/
│   └── SKILL.md
```

Every SKILL.md must start with YAML frontmatter (opencode format shown, compatible with other harnesses):

```yaml
---
name: <skill-name>
description: <brief description of what this skill does>
license: MIT
compatibility: opencode
metadata:
  type: <command-skill | infrastructure | workflow>
  source: <relevant source command or tool>
---
```

Use `.agents/templates/skill.md` as the starting point — it has the correct frontmatter structure and section layout.

After the frontmatter, the body follows this structure:

```markdown
# Skill: <Human Readable Title>

## Purpose
[What this skill helps with — 1-3 sentences]

## Prerequisites
[Any tools, permissions, or context needed]

## Execution
[Step-by-step guide with concrete commands and examples]

### [Step 1]
[Detailed instructions with commands]

### [Step 2]
...

## Common Pitfalls
[Things to watch out for]

## Examples
[Real-world usage examples if applicable]
```

## How to Create a Skill

1. Read the template: `Read .agents/templates/skill.md`
2. Identify the recurring pattern or workflow
3. Create the directory: `mkdir -p .agents/skills/<name>/`
4. Copy the template structure and fill in all fields — keep the frontmatter intact
5. Document concrete commands and examples — not abstract principles
6. List the new skill in `.agents/skills/` directory structure

## How to Update an Existing Skill

1. Read the current skill: `Read .agents/skills/<name>/SKILL.md`
2. Add the new pattern, gotcha, or example
3. Preserve existing content — only add or refine
4. Update the `## Common Pitfalls` section if a new mistake was discovered

## How Agents Load Skills

Agents load skills differently depending on the harness:

```
# Native skill loading (harness-dependent):
#   opencode: skill({ name: "<skill-name>" })
#   claude:   Read .agents/skills/<skill-name>/SKILL.md
#   generic:  Read .agents/skills/<skill-name>/SKILL.md
```

If you don't know the harness, list the directory and read directly — always works:

```
ls .agents/skills/
Read .agents/skills/<name>/SKILL.md
```

When delegating to a subagent, tell it to load the relevant skill by name. If you don't know the subagent's harness, just tell it to read the file directly.

## When NOT to Create a Skill

- The pattern is already fully covered by an existing skill
- The pattern is a one-off operation unlikely to repeat
- The information belongs in a project rule (`.agents/rules/`) instead
- The pattern is already documented in `.agents/rules/`

## Review and Validation

After creating or updating a skill, the orchestrator should:

1. Verify the YAML frontmatter is present and correct (name, description, license, compatibility, metadata)
2. Verify the skill file follows the template structure from `.agents/templates/skill.md`
3. Confirm all commands in the skill actually work
4. Check that the skill doesn't duplicate existing skills or rule files
5. Commit the new skill with a message like `feat(skills): add <name> skill`

## Examples of Good Skill Candidates

- "Deploying to staging" — steps to build, tag, push, and verify
- "Running performance benchmarks" — tools, flags, and interpretation
- "Setting up a new subproject" — common configuration steps
- "Database migration patterns" — Alembic or similar workflow
- "API testing with curl/httpie" — patterns for manual API testing
