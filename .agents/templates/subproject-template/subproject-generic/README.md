# Subproject Template

This template provides the baseline structure for new subprojects. Copy this directory to `src/<subproject>/` when creating a new subproject.

## Folder Structure

```
<subproject>/                    # lower-kebab-case subproject folder
├── <source_dir>/                # source code directory (lower_snake_case — rename per your language convention)
│   └── <module>/                # domain/feature module
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
├── project.config.toml          # generic config — rename/adapt for your language
└── README.md
```

**Key rules:**
- The config file (`.config.toml`, `pyproject.toml`, `package.json`, etc.) lives at the subproject root, alongside the source folder.
- Each domain/feature area gets its own module inside the source directory.
- Source directory naming follows your language's convention (e.g., `snake_case` for Python, `kebab-case` for JavaScript).

## Setup Instructions

1. Copy to `src/<subproject>/`
2. Rename the source directory to match your subproject name following your language's naming convention
3. Adapt the config file for your language/toolchain:
   - **Python**: rename `project.config.toml` → `pyproject.toml` and configure
   - **Node.js**: create `package.json` (or adapt the config as reference)
   - **Rust**: rename `project.config.toml` → `Cargo.toml`
   - **Go**: create `go.mod`
4. Update `Makefile` targets for your package manager and test runner
5. Install dependencies:
   ```bash
   make install
   ```
6. Run tests:
   ```bash
   make test
   ```
