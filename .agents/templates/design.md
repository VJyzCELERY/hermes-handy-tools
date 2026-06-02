# Design Document: [FEATURE NAME]

**Spec**: [Link to corresponding spec.md]
**Status**: Draft | In Progress | Complete
**Last Updated**: YYYY-MM-DD

---

## Overview

One-paragraph synopsis: what this changes, which subprojects are affected, and the key architectural decision.

---

## Architecture

### Component Overview

Describe the high-level components involved and how they interact. Use ASCII diagrams when helpful.

```
[Client] --> [API Layer] --> [Service Layer] --> [Data Layer]
                                  |
                            [External Service]
```

### Affected Components

| Component | Change Type | Notes |
|-----------|-------------|-------|
| [module/class] | New / Modified / Deleted | [brief description] |

---

## Data Model

### New Entities _(if applicable)_

```python
# Conceptual data shape (not necessarily the final class)
UserProfile:
    id: str           # unique identifier
    email: str        # validated email address
    created_at: datetime
```

### Schema Changes _(if applicable)_

- Describe any changes to existing data structures
- Document migration strategy if existing data is affected
- List backward compatibility implications

---

## API / Interface Contracts

### New / Modified Endpoints or Functions

```python
# Signature and contract description
def create_user(email: str, role: str = "viewer") -> UserProfile:
    """
    Create a new user account.
    Raises ValueError if email is invalid or already registered.
    """
```

### Error Handling

| Error Case | Exception / Response | Notes |
|------------|---------------------|-------|
| Invalid email | `ValueError("Invalid email")` | |
| Duplicate user | `ConflictError("User already exists")` | |

---

## Implementation Phases

### Phase 1 — MVP _(required for initial release)_

- [ ] [Task 1 description]
- [ ] [Task 2 description]

### Phase 2 — Enhancements _(post-MVP, only if spec explicitly includes it)_

- [ ] [Task description]

> **Note**: Phase 2 must NOT be implemented until Phase 1 is complete and reviewed.

---

## Technical Decisions

Document key decisions and the reasoning behind them:

1. **Decision**: [e.g., "Use a flat table rather than a nested structure"]
   - **Reason**: [e.g., "Simpler queries, spec does not require hierarchical data"]
   - **Alternatives Considered**: [e.g., "Nested JSON — rejected because it complicates filtering"]

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| [Risk description] | Low/Med/High | Low/Med/High | [mitigation strategy] |

---

## Open Questions _(optional)_

Design-level questions not yet resolved:

1. [Question and current thinking]

---

## References

- Spec: `./spec.md` — relative path from this design.md to its spec.md (they live in the same directory)
- Related designs: [paths to related design docs if any]
