# Review Log: {branch_name}

---

[REVIEW_{entry_id}_START]
---

**Review Date**: {date}
**Scope**: {scope}
**Cycle**: {cycle}
**Total Findings**: {total} | **Resolved**: {resolved} | **Deferred**: {deferred} | **Invalid**: {invalid}

---

{findings}

---

[REVIEW_{entry_id}_END]
---

## Finding Entry Format

Each finding follows this structure:

### F-{id}: {Short Description}
- **Severity**: {severity} | **Category**: {category}
- **Status**: {addressed | invalid | deferred}
- **Problem**: {description of the issue}
- **Validation**: {how the issue was validated}
- **Resolution**: {what was done to fix}
- **Reasoning**: {why this fix was chosen}
