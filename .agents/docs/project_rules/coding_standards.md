# Coding Standards

## Updated Rules
1. **Global Enforcements**:
   - **Code Style**: Ruff manages all linting and formatting tasks.
   - **Auto-Fix**: Ruff is configured to auto-fix all known issues (`fixable = ["ALL"]`).
   - **Absolute Imports**: Relative imports are disallowed (`ban-relative-imports = "all"`).

2. **Logging Practices**:
   - Use `logging` for debugging and messaging across all subprojects.
   - Follow centralized logging rules as detailed in `.agents/docs/project_rules/logging_guidelines.md`. 
   - Test directories are exempt from docstring rules (see Ruff config in `.agents/docs/agents/style.md`).

---

## Docstring Guide

Use Google-style docstrings for all public functions and classes (see `.agents/docs/agents/style.md` for the full format).