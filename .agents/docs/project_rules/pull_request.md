# Pull Request Guidelines

## PRs Must Be Based on Spec and Design

Every PR must correspond to a feature spec (`spec.md`) and design document (`design.md`). The PR description, scope, and implementation must remain synchronized with these source documents.

### Before Creating a PR

1. **Verify spec and design exist**: The feature being PR'd must have a corresponding `spec.md` and `design.md` in `specs/<feature-name>/` or `src/<subproject>/specs/<feature-name>/`.
2. **Check implementation against spec**: Every functional requirement (FR-001, FR-002, etc.) in the spec must be addressed in the PR. If a requirement is intentionally deferred, note it explicitly.
3. **Check implementation against design**: The code structure, API contracts, and data model must match the design document. If the design is outdated, update it before creating the PR.

### When Changes Drift from Spec/Design

If during implementation the solution diverged from the original spec or design:

1. **Update spec.md**: If requirements changed, update the spec to reflect current reality.
2. **Update design.md**: If architecture or data model changed, update the design doc.
3. **Link the updates**: Reference the updated spec/design in the PR body.

**All three documents (spec, design, implementation) must be consistent at PR time.**

### PR Body Requirements

- Reference the spec and design: `Spec: specs/<feature-name>/spec.md`
- Reference the issue/PR number if applicable
- List what was in scope vs out of scope (mapped to spec FRs)
- Include testing steps that verify spec acceptance criteria
- Flag any deviations from spec or design with rationale

### What to Review in a PR

- Spec compliance: does the implementation satisfy the spec?
- Design fidelity: does the implementation follow the design?
- Test coverage: are spec acceptance scenarios covered?
- Scope discipline: no Phase 2 features in an MVP PR

### Template

Use `.agents/templates/PR-body.md` as the starting point. Always reference spec and design in the PR summary.
