"""Tests for PR body template validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEMPLATE_PATH = Path(__file__).parents[3] / ".agents" / "templates" / "PR-body.md"


class TestValidatePrBody:
    def _validate(self, body: str) -> list[str]:
        from importlib import reload
        import gh
        reload(gh)
        return list(gh.validate_pr_body(body))

    def test_rejects_empty_body(self):
        errors = self._validate("")
        assert errors

    def test_rejects_missing_all_sections(self):
        errors = self._validate("# Just a title")
        assert errors
        assert any("Summary" in e for e in errors)
        assert any("How to Test" in e for e in errors)

    def test_rejects_unfilled_placeholder(self):
        body = """## Summary

[Describe the problem being solved.]

## How to Test

1. Run tests.

## Review Notes

[What to review closely]

## Related Issues

None."""
        errors = self._validate(body)
        assert any("placeholder" in e.lower() for e in errors)

    def test_accepts_filled_body(self):
        body = """## Summary

### Problem
Users couldn't authenticate via OAuth.

### Solution
Added OAuth flow with Google provider.

## How to Test

1. Run tests:
   ```bash
   cd src/my-subproject && uv run pytest
   ```

## Review Notes

- `src/my-subproject/auth.py` — OAuth flow implementation

## Related Issues

- None"""
        errors = self._validate(body)
        assert not errors, f"Unexpected errors: {errors}"

    def test_rejects_missing_section(self):
        body = """## Summary

### Problem
Something.

## How to Test

1. Test."""
        errors = self._validate(body)
        assert any("Review Notes" in e for e in errors)
        assert any("Related Issues" in e for e in errors)

    def test_accepts_minimal_valid_body(self):
        body = """## Summary

### Problem
Fixed login bug.

### Solution
Updated token refresh logic.

## How to Test

1. Run `uv run pytest`

## Review Notes

- OK

## Related Issues

- None"""
        errors = self._validate(body)
        assert not errors, f"Unexpected errors: {errors}"


def test_pr_body_template_has_current_document_reference_slots():
    content = TEMPLATE_PATH.read_text(encoding="utf-8")

    for label in ("Spec", "Design", "Implementation Plan", "Tasks"):
        assert f"**{label}**" in content
