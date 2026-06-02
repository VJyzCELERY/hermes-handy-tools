# Python Subproject Template

This template provides the baseline structure for new Python subprojects. Copy this directory to `src/<subproject>/` when creating a new Python subproject.

## Folder Structure

```
<subproject>/                    # lower-kebab-case subproject folder
├── <python_package>/            # lower_snake_case Python package
│   ├── __init__.py
│   └── <module>/                # domain/feature subpackage
│       └── __init__.py
├── tests/
│   ├── unit/
│   └── integration/
├── specs/
│   ├── README.md
│   └── <feature-name>/
│       ├── spec.md
│       └── design.md
├── docs/
│   ├── agents/
│   └── examples/
├── AGENTS.md
├── Makefile
├── pyproject.toml               # subproject root — NOT inside the package
└── README.md
```

**Key rules:**
- `pyproject.toml` lives at the subproject root, alongside the package folder.
- Each domain/feature area gets its own subpackage inside the package.
- Every subpackage must have an `__init__.py`.
- Subpackage names use `lower_snake_case`.

## Setup Instructions

1. Copy to `src/<subproject>/`
2. Rename `<python_package>/` to match your subproject name in `lower_snake_case`
3. Install dependencies:
   ```bash
   make install
   ```
4. Run tests:
   ```bash
   make test
   ```
