# Feature Specification: [FEATURE NAME]

**Status**: Draft | In Progress | Complete | Deprecated
**Created**: YYYY-MM-DD
**Last Updated**: YYYY-MM-DD
**Subproject(s) Affected**: [e.g., my-subproject-backend, my-subproject-sdk]

---

## Problem Statement _(mandatory)_

- **Goals**: Provide [capability] so [persona/caller] can [outcome].
- **Gaps**: What is broken or missing today.
- **Non-Goals**: Explicitly out of scope — what this spec does NOT cover.
- **Constraints**: Contracts to honor, existing APIs, backward compatibility requirements.

---

## User Scenarios & Testing _(mandatory)_

### Primary Scenario

[Describe the main user journey or API usage flow in plain language]

### Acceptance Scenarios

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

### Edge Cases

- What happens when [boundary condition]?
- How does the system handle [error scenario]?
- What is the behavior with empty/null inputs?

---

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: System MUST [specific capability]
- **FR-002**: System MUST [specific capability]
- **FR-003**: Users/callers MUST be able to [key interaction]

_Example of marking unclear requirements:_
- **FR-004**: System MUST authenticate via [NEEDS CLARIFICATION: auth method not specified — API key, OAuth, session?]
- **FR-005**: System MUST retain data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities _(include if feature involves data)_

- **[Entity 1]**: What it represents, key attributes (no implementation details)
- **[Entity 2]**: What it represents, relationships to other entities

---

## Success Criteria _(mandatory)_ — use `[ ]` checkboxes

Objective, measurable checks that prove the problem is solved.

- [ ] **User can [action]**: [specific verifiable capability]
- [ ] **System handles [scenario]**: [specific measurable behavior]
- [ ] **Performance**: [if applicable — e.g., "response time < 200ms for 99th percentile"]

---

## Testing Plan _(mandatory)_

### Unit Tests

- [What unit tests will cover]
- [Key functions/classes to test]

### Integration Tests

- [What integration tests will cover]
- [Key workflows to test end-to-end]

### Manual Tests _(if applicable)_

- [Key scenarios to verify manually]

---

## Status Tracker _(optional)_

| Item | Status | Notes |
|------|--------|-------|
| [Component] | TODO / In Progress / Done | [notes] |

---

## Open Questions _(optional)_

1. **[Question]**
   - **Owner**: @username
   - **Target**: YYYY-MM-DD
   - **Status**: Discussion / Proposed / Decided
   - **Proposed Answer**: [if any]

---

## Review Checklist

- [ ] No implementation details (no code, framework, or architecture choices)
- [ ] All mandatory sections completed
- [ ] No `[NEEDS CLARIFICATION]` markers remain
- [ ] Requirements are testable and unambiguous
- [ ] Scope is clearly bounded with explicit non-goals
- [ ] Success criteria are measurable
