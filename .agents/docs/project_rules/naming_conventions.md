# Naming Conventions

This document defines the naming conventions for the MAIN-PROJECT and its subprojects.

## Convention Reference

Throughout the project documentation, these placeholders are used. Each maps to a specific naming rule:

| Placeholder | Represents | Convention | Example |
|-------------|-----------|------------|---------|
| `<subproject>` | Subproject directory under `src/` | `lower-kebab-case` | `my-subproject` |
| `<subproject-dir>` | Same as `<subproject>` (used in path examples) | `lower-kebab-case` | `my-subproject` |
| `<source_dir>` | Source code directory inside subproject (generic) | Per-language convention | `<python_package>` |
| `<python_package>` | Python package directory inside subproject | `lower_snake_case` | `my_subproject` |
| `<module>` | Domain/feature subpackage inside the source directory | `lower_snake_case` | `clients`, `models`, `tools` |
| `<feature-name>` | Feature spec/design folder | `lower-kebab-case` | `user-authentication` |

## Subproject Naming

1. Each subproject folder uses `lower-kebab-case`:
   - Directory: `src/<subproject>/`
   - Example: `src/my-subproject/`
2. The corresponding source code folder inside a subproject follows your language's convention:
   - **Python**: `src/<subproject>/<python_package>/` (e.g., `src/my-subproject/my_subproject/`)
   - **Generic**: `src/<subproject>/<source_dir>/` (use `<source_dir>` as a placeholder in docs)

## Module / Subpackage Naming

1. Domain/feature subpackages inside the source directory use `lower_snake_case`:
   - **Python**: `<source_dir>/<module>/` (e.g., `my_subproject/clients/`)
   - For other languages, follow your language's convention for module/directory naming.

## File Naming Conventions

1. Python files use `snake_case`:
   - Example: `my_module.py`
2. Test files are prepended with `test_`:
   - Example: `test_main.py`

## Feature Spec Naming

1. Feature spec/design folders use `lower-kebab-case`:
   - Directory: `specs/<feature-name>/`
   - Example: `specs/user-authentication/`
