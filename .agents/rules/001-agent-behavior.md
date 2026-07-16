---
description: Planning and implementation behavior, security, and documentation standards
globs: "*"
alwaysApply: false
---

# Agent Behavior

## Scope Discipline

- Prefer the simplest solution that satisfies the spec.
- Implement only requested behavior; avoid speculative flexibility, layers, dependencies, and optimization.
- Stop at the first sufficient option: deletion, standard library, native platform capability, an existing dependency, then the minimum new code.
- Do not add abstractions, configuration, extension points, caching, concurrency, or dependencies for hypothetical future needs.
- Challenge gaps or contradictions before implementation. Do not silently reinterpret the spec.
- Keep security controls, validation, data-loss prevention, accessibility, and permission gates intact.

## Technical Debt And Stubs

- Record an intentional compromise as `[DEBT][DEBT-XXXXXXXX]: <shortcut and reason> | trigger: <objective cleanup condition>` in the host language's comment syntax. Generate the stable ID with `/debt new`; `XXXXXXXX` is eight uppercase hexadecimal characters.
- The ID exists before any issue. Issues include the exact ID in their title and body, so source markers never change merely to link remote tracking. Multiple markers may share an ID only when they represent the same debt and intentionally share one issue.
- Remove all associated markers when the debt is resolved. Use `/debt harvest DEBT-XXXXXXXX` when public tracking is warranted; it must resolve existing open and closed issues before creating one.
- Debt must state the current compromise and an objective trigger, not vague intent such as "later". Bugs and missing correctness, security, accessibility, trust-boundary validation, data-loss prevention, or permission controls are not deferrable debt.
- Production stubs are prohibited by default. If requested scope explicitly requires a temporary stub, place a valid debt marker adjacent to it and explain the intended replacement and cleanup trigger. Test doubles and intentional abstract/interface methods are not production stubs.

## Security

- Never hardcode or expose secrets, credentials, tokens, private keys, or sensitive personal data.
- Validate untrusted API, CLI, file, and environment input at the boundary.
- Use parameterized data access and safe process/path APIs; prevent injection and traversal.
- Do not expose stack traces, internal paths, or sensitive values to end users or logs.
- Review new dependencies for necessity, maintenance, and known vulnerabilities.

## Documentation

- Update affected public, operational, and API documentation when behavior changes.
- Remove stale references when files, APIs, or features are removed or renamed.
- Document required environment variables with placeholders, never real credentials.
