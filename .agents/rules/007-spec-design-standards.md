---
description: Standards for writing spec.md and design.md documents — template usage, what to include, what to exclude
globs: "*.md"
alwaysApply: false
---

# Spec & Design Standards

## Critical: Templates Are OUTPUT Guides, NOT Instruction Documents

The template files (`.agents/templates/spec.md` and `.agents/templates/design.md`) contain **only the output structure** — they define what the final document should look like. All agent instructions for *how* to write these documents live HERE in this rule file.

**NEVER include any of the following in the output document:**
- YAML front matter (unless the template explicitly shows content-relevant front matter like `title:`)
- HTML comments (`<!-- ... -->`)
- Agent instructions, guidelines, or meta-notes
- Instructional blockquotes telling the agent what to do

## Writing Specs (`spec.md`)

### Purpose
A spec defines **WHAT** users/callers need and **WHY** — not HOW to implement.

### Core Guidelines
- Focus on what and why. Avoid implementation details (no tech stack choices, class names, or code structure).
- Mark unclear requirements with `[NEEDS CLARIFICATION: specific question]`.
- Every requirement must be independently testable.
- Highlight anything that could violate KISS, YAGNI, or DRY for architecture review.
- When done, requirements with `[NEEDS CLARIFICATION]` markers must be resolved before implementation begins.
- Spec and design are a pair — `design.md` MUST be created in the same directory as `spec.md`.

### Mandatory Sections
- Problem Statement (Goals, Gaps, Non-Goals, Constraints)
- User Scenarios & Testing
- Requirements (Functional + Key Entities)
- Success Criteria (checkbox format)
- Testing Plan

## Writing Designs (`design.md`)

### Purpose
A design defines **HOW** — the architecture, data model, API contracts, and implementation phases.

### Core Guidelines
- This design must be paired with a `spec.md` in the same directory. The spec defines WHAT and WHY; this design defines HOW.
- Focus on architecture, data model, API contracts, and implementation phases.
- Keep decisions documented: explain WHY an approach was chosen, not just WHAT.
- Include error handling, edge cases, and failure modes in API contracts.

### Mandatory Sections
- Overview (one-paragraph synopsis)
- Architecture (components, interactions, affected components table)
- Data Model (new entities, schema changes)
- API / Interface Contracts (endpoints, error handling table)
- Implementation Phases (at minimum Phase 1 — MVP)
- Technical Decisions (with alternatives considered)
- Risks & Mitigations

## Using Templates Correctly

1. **Read the template** to understand the output structure.
2. **Do NOT copy YAML front matter, HTML comments, or instructional text** from the template into the output — these are instructions for you, not content.
3. **Replace all placeholders** like `[FEATURE NAME]`, `YYYY-MM-DD`, `[specific capability]` with meaningful content.
4. **Remove any section** that has no content rather than leaving it empty with placeholder text (e.g., if there are no manual tests, omit the Manual Tests section entirely).
5. **Status field**: Start with `Draft`, update to `In Progress` as you fill it in, and mark `Complete` when all sections are filled and reviewed.

## Common Mistakes to Avoid

| Mistake | Why It's Wrong | Fix |
|---------|---------------|-----|
| Keeping `[FEATURE NAME]` as-is | Leaves placeholder in output | Replace with actual feature name |
| Copying `agent_guidelines` YAML | Agent instructions become document content | Omit entirely — this file IS your instruction |
| Copying HTML comments like `<!-- id: 0 -->` | Tracking IDs not meaningful to readers | Omit from output |
| Including "Spec and design are a pair" note | It's an instruction to create both, not spec content | Omit — the spec doesn't need to tell itself to pair |
| Leaving `YYYY-MM-DD` as placeholder | Looks incomplete | Replace with actual date or remove if auto-tracked |
| Including instructional blockquotes | Makes document read like agent notes | Omit or replace with real content |
