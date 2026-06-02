# Project Structure

## Overview
The `MAIN-PROJECT` is organized to facilitate modular subproject development and collaboration. Below is the general structure:

```
MAIN-PROJECT/
├── docs/                          # Main documentation
├── specs/                         # Project-level feature specs
│   ├── spec-template.md           # Symlink → .agents/templates/spec.md
│   ├── design-template.md         # Symlink → .agents/templates/design.md
│   └── <feature-name>/            # One folder per feature
│       ├── spec.md
│       └── design.md
├── src/                           # Subprojects
│   └── <subproject>/              # lower-kebab-case subproject folder
│       ├── <python_package>/      # lower_snake_case Python package
│       │   ├── __init__.py
│       │   └── <module>/          # domain/feature subpackage
│       │       └── __init__.py
│       ├── tests/
│       │   ├── conftest.py
│       │   ├── fixtures/
│       │   ├── unit/
│       │   │   ├── conftest.py
│       │   │   └── test_*.py
│       │   └── integration/
│       │       ├── conftest.py
│       │       └── test_*.py
│       ├── specs/
│       │   ├── README.md
│       │   └── <feature-name>/
│       │       ├── spec.md
│       │       └── design.md
│       ├── docs/
│       │   ├── agents/
│       │   ├── development/
│       │   └── examples/
│       ├── AGENTS.md
│       ├── Makefile
│       ├── pyproject.toml         # subproject root — NOT inside the package
│       ├── README.md
│       └── uv.lock
├── .agents/                       # Agent configuration (commands, templates, docs, skills)
├── AGENTS.md
├── Makefile
├── PROJECT-GUIDELINES.md
└── README.md
```

Subprojects inherit coding standards and documentation rules from the MAIN-PROJECT but may define specific rules in their own `docs/` folder.

---

## Package Internal Layout

The Python package sits at the same level as `pyproject.toml`, not inside it. Domain/feature areas are organised as subpackages (modules):

```
<python_package>/
├── __init__.py
├── <module>/          # domain/feature subpackage
│   ├── __init__.py
│   └── ...
└── <module>/          # additional domain subpackages as needed
    ├── __init__.py
    └── ...
```

Rules:
- `pyproject.toml` lives at the **subproject root** — never inside the package folder.
- Each domain/feature area gets its own subpackage.
- Every subpackage must have an `__init__.py`.
- Subpackage names use `lower_snake_case`.

---

## Specs and Design Convention

Both the project root and each subproject use the same folder-per-feature convention:

| Location | When to use |
|---|---|
| `specs/<feature-name>/` | Cross-subproject or project-wide features |
| `src/<subproject>/specs/<feature-name>/` | Features scoped to a single subproject |

**Rule**: Never create a flat `spec.md` or `design.md` directly under a `specs/` folder.
Always use a named subfolder with `lower-kebab-case`.

---

## Standard Makefile for Subprojects
All subprojects must include a `Makefile` to simplify common operations. Below are the predefined targets:

- **install**: Installs all dependencies.
- **lint**: Runs the linter (Ruff) for code style checks.
- **test**: Runs the test suite using pytest.
- **coverage**: Runs tests with code coverage and generates an HTML report.
- **complexity**: Runs cognitive complexity analysis (radon).
- **clean**: Removes temporary files, artifacts, and caches.

#### Example Usage:
```bash
# Install dependencies
make install

# Run linting
make lint

# Run tests
make test

# Check coverage
make coverage

# Run complexity audit
make complexity

# Clean the project
make clean
```
