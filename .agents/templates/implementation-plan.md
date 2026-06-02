# Implementation: [Feature Name]

[Brief description of what this implementation accomplishes. What problem does it solve? What user need does it address?]

## Context

- **Spec Reference**: [link to spec.md or description]
- **Design Reference**: [link to design.md or description]
- **Priority**: [P0|P1|P2|P3]
- **Estimated Effort**: [XS|S|M|L|XL]

## Environment Pre-requisites

List everything that must be set up before the implementation and tests can run. This ensures the developer (agent or human) has a working environment from the start.

> If no special environment setup is needed, mark this section as **N/A** and remove the checklist items below. Do not leave empty checkboxes.

### Configuration

- [ ] **.env file** — required variables:
  ```
  # [Service/API Name]
  API_KEY=xxx
  API_URL=http://localhost:8000
  DATABASE_URL=postgresql://user:pass@localhost:5432/db
  ```
- [ ] **Environment variables** documented in [path/to/.env.example or docs]
- [ ] **Secrets/credentials** needed (API tokens, service accounts)
- [ ] **None** — this feature has no configuration dependencies

### Running Services

| Service | Required | How to Start | Health Check |
|---------|----------|--------------|--------------|
| [e.g., PostgreSQL] | Yes / No | `docker compose up -d db` | `pg_isready` |
| [e.g., Redis] | Yes / No | `docker compose up -d redis` | `redis-cli ping` |
| [e.g., API server] | Yes / No | `uv run uvicorn app.main:app` | `curl localhost:8000/health` |
|- [ ] **None** — no external services needed

### Data / Fixtures

- [ ] **Test database migrations**: `uv run alembic upgrade head`
- [ ] **Seed data** loaded: `uv run python scripts/seed.py`
- [ ] **Mock external services** if applicable (e.g., WireMock, localstack)
- [ ] **None** — no data or fixtures needed

### Access / Permissions

- [ ] [User account / API key / OAuth token needed]
- [ ] [Firewall rules / VPN / Tailscale access]
- [ ] **None** — no special access required

### Developer Tooling

- [ ] **Runtime**: Python [version], Node [version], Docker [version]
- [ ] **Package manager**: uv / pip / npm
- [ ] **Additional CLI tools**: [e.g., jq, aws-cli, httpie]
- [ ] **None** — no special tooling required

---

## Success Criteria — Integration Tests (TDD First)

Define the integration tests that prove the feature works. These are written FIRST — before any implementation code. The implementation is only complete when these tests pass.

```python
# Test file: [path/to/test_file.py]
"""Integration tests for [feature name]."""


def test_[scenario_under_test]:
    """[Describe what this test verifies]"""
    # Arrange
    [setup code]
    # Act
    [action code]
    # Assert
    [assertion code]


def test_[another_scenario]:
    """[Describe]"""
    # Arrange
    [setup]
    # Act
    [action]
    # Assert
    [expected outcome]
```

### Key Test Scenarios

- [ ] **Scenario 1**: [description of what the test covers and why it's the primary success criterion]
- [ ] **Scenario 2**: [description]
- [ ] **Edge case**: [description]

## Verification Plan

### Automated Tests

- [ ] Integration tests (defined above) — these must pass for implementation to be complete
- [ ] Unit tests for [module/component] — test error handling, edge cases, fallbacks
- [ ] Existing test suite — confirm no regressions: `uv run pytest`

### Manual Verification

- [ ] [Verification step 1]
- [ ] [Verification step 2]

### Performance Considerations

- [ ] [Performance test or check]
- [ ] [Load test if applicable]

## Proposed Changes

### [Module/Section Name]

#### [ACTION] [File Path]

- **[Description of change]**: [What specifically needs to be modified]
- **[Rationale]**: [Why this change is needed]

#### [Another ACTION] [File Path]

- **[Description of change]**
- **[Rationale]**

### [Another Module/Section Name]

#### [NEW] [new/file/path.py]

- **[Description]**: [What new component or module needs to be created]
- **[Dependencies]**: [What other modules it depends on]

#### [MODIFY] [existing/file.py]

- **[Description of change]**
- **[Breaking changes if any]**

## Architecture Changes

| Component | Change Type | Description |
|-----------|-------------|-------------|
| [Component A] | Modify | [What changed] |
| [Component B] | New | [What's added] |
| [Component C] | Remove | [What's being removed] |

## Data Model Changes

```python
# New types or modified interfaces
[NewType]:
    field1: str
    field2: int
```

## API Changes

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/resource | Create new resource |
| GET | /api/v1/resource/:id | Get resource by ID |

### Modified Endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | /api/v1/existing | Added new query parameter |

## Dependencies

### External Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| [package-name] | ^1.0.0 | [reason] |

### Internal Dependencies

- [ ] Depends on [other implementation]
- [ ] Blocks [other feature]

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| [Risk description] | [High/Medium/Low] | [Mitigation strategy] |

---

*Generated from spec.md and design.md*
*Last updated: [ISO Date]*
