# Code Review Standards

Rules for reviewing code, identifying issues, and providing feedback.

---

## Core Review Principles

- **Always Compare to `main`**: All diffs and comparisons must be against the `main` branch (the primary branch)
- **Verify the baseline**: Capture the `main` commit hash before diffing, note the merge base when a target branch is provided, and include both staged and unstaged changes when reviewing a working tree
- **Require Spec Before Review**: If no spec file is found, ask the user to provide it before proceeding with full review
- **Minimum Viable Implementation**: Verify code implements spec requirements with the least complexity possible
- **Focus on Overengineering**: Actively look for unnecessary complexity, excessive helper functions, and over-abstraction
- **Check Spec Compliance**: When reviewing features, find and read the relevant spec file first, then compare implementation
- **Code vs Docs Mismatch**: If the implementation is correct but the docs say something different, the docs need updating. If the implementation fails to meet the docs' requirements, the code needs fixing
- **YAGNI Principle**: Flag any code that goes beyond spec requirements without clear, documented justification
- **Documentation equals code**: Documentation changes are as important as code changes. Flag missing or stale docs with the same priority as code bugs
- **Impact first**: Prioritize findings with material impact; only raise style issues when they affect clarity, correctness, or consistency
- **Cite evidence**: Reference findings with `file:line` (from the diff) so fixes are traceable
- **Focus on Actionable Feedback**: Every comment should include a specific recommendation
- **Prioritize by Impact**: Order findings from most critical to least critical
- **Be Constructive**: Balance criticism with recognition of good practices

---

## Clean Code Characteristics

When reviewing code, apply these principles:

1. **Readable**: Code should be immediately clear to another developer; purpose and logic should be obvious
2. **Simple**: Avoid unnecessary complexity in both logic and structure
3. **Expressive**: Variable, function, and class names should be meaningful and reflect the problem domain
4. **Consistent**: Follow consistent naming conventions, coding styles, and design patterns throughout
5. **Minimal**: Eliminate redundancy; every part of the code should serve a clear purpose
6. **Testable**: Structure code to facilitate automated testing
7. **Well-Structured**: Organize code logically with clear relationships between components
8. **Adaptable**: Design should be flexible and easy to modify for incremental changes

---

## Overengineering & Simplification Review (CRITICAL FOCUS)

### Minimum Viable Implementation
- Does the code implement the spec requirements with the least complexity?
- Could simpler code satisfy the same requirements?

### Excessive Helper Function Fragmentation
- Count helper functions per file (flag if >20 helper functions in a single file)
- Identify single-use wrappers that add no value (functions called only once)
- Check if helper functions could be consolidated into a utility class or module
- Verify if helpers are shared across modules (if yes, keep separate; if no, consider inlining)

### Unnecessary Abstraction Layers
- Look for intermediate dataclasses/classes that don't add clarity or validation
- Flag wrapper classes that only pass through to another class
- Identify factory patterns used for simple object creation

### Overly Complex Logic
- Identify areas where simple operations are broken into too many steps (>5 steps for a simple operation)
- Flag nested conditionals (>3 levels deep) that could be simplified
- Check for complex regex or string manipulation that could use simpler methods

### Code Duplication
- Identify repeated patterns across modules (extract to shared utilities)
- Check for copy-paste code blocks (>10 lines duplicated)

### Unused Code
- Identify functions/classes that are defined but never called
- Flag commented-out code blocks that should be removed
- Check for unused imports or variables

### Premature Optimization
- Look for complex solutions to simple problems (e.g., caching for rarely-called functions)
- Flag micro-optimizations that hurt readability
- Check for unnecessary async/await patterns

### Beyond Spec Requirements
- Flag any implementation that exceeds spec requirements without documented justification
- Check for "future-proofing" or "extensibility" features not mentioned in spec
- Verify Phase 2 features are not implemented in MVP

---

## Review Focus Areas

### Code Quality & Design
- Clear, meaningful names for functions and variables
- Small, focused functions and clean control flow
- Consistent formatting and idiomatic style
- SOLID principles and modular design
- Avoids deep nesting and duplicated logic

### Cognitive Complexity
- All functions must have a complexity score of **15 or below** (see `.agents/docs/project_rules/cognitive_complexity.md`)
- Flag any function that would fail `make lint` (Ruff C901)
- Suggest refactors: early returns, extracted helpers, lookup tables

### Security (High Priority)
- **Input validation and sanitization**: Ensure all user inputs are properly validated and sanitized
- **SQL injection prevention**: Verify use of parameterized queries and proper escaping
- **XSS prevention**: Check for proper output encoding and input filtering
- **Authentication/authorization**: Review access controls and permission checks
- **Sensitive data handling**: Ensure no hardcoded secrets, proper encryption usage, secure storage
- **Error handling**: Verify sensitive information is not leaked in error messages
- **Dependency vulnerabilities**: Check for known CVEs in dependencies
- **CSRF prevention**: Verify CSRF protection for state-changing operations (if applicable)

### Performance Considerations
- Algorithm complexity analysis
- Database query optimization
- Memory usage patterns
- Resource cleanup and leak prevention (file handles, network clients, event hooks)
- Caching opportunities

### Testing Coverage
- **Unit test coverage**: Verify new functions/classes have corresponding unit tests
- **Integration test coverage**: Verify new API endpoints have integration tests
- **Edge case handling**: Verify null/None handling, empty string/list/dict handling, boundary conditions
- **Error condition testing**: Verify error paths are tested (exceptions, failures)
- **Test execution**: Ensure test suites run from component roots (`make test`)

### Documentation (Equal Priority to Code)
- **Spec/design sync**: Verify implementation matches the spec and design — flag any drift
  - Implementation better than docs → docs need updating (file a docs finding)
  - Implementation fails to meet docs → code needs fixing (file a code finding)
- **API docs**: New endpoints, functions, or classes must have corresponding docstrings and docs
- **README/guides**: Feature changes must update relevant README or guide files
- **Stale docs**: Flag documentation that references removed/renamed code
- **Docstring completeness**: All public functions and classes must have Google-style docstrings

### Maintainability
- Easy to read and extend
- Clear separation of concerns
- Clean abstraction boundaries
- Manageable dependencies
- Follows project architecture

---

## Spec Compliance Review (CRITICAL FOCUS)

- **Identify relevant spec files**: Look for `.md` files in `specs/` that relate to the changes
- **Read the spec**: Understand what was required vs what was implemented
- **Check for spec compliance gaps**: Identify features mentioned in spec but not implemented
- **Check for over-implementation**: Identify features implemented that are not in the spec
- **Verify MVP scope**: Ensure Phase 2 features are not implemented in MVP
- **Minimum code changes principle**: Verify implementation uses the simplest approach that satisfies spec requirements
- **Cross-reference with implementation**: Compare spec requirements line-by-line with code

---

## Review Format

### Initial Summary
Start with a **2-3 sentence summary** covering:
- Overall impression
- Major strength(s) or concern(s)
- Scope/complexity notes (e.g., "large refactor", "adds new API", etc.)

### Detailed Feedback Format
Use this structure when pointing out improvements:

```
[File:Line] Issue: Brief description of the problem
Why it matters: (e.g. readability, performance, security, maintainability)
Suggestion: Specific fix or pattern, optionally with code
```

Also include:
```
Strengths:
- [File:Line] Good use of pattern X
- Clear logic in [ModuleName]
```

### Recommendations Block
End with 3-5 prioritized, actionable improvements:

```
Recommendations

Priority 1 (Critical):
- [File:Line] Risk of SQL injection - use parameterized queries instead

Priority 2 (High):
- [File:Line] Missing input validation may allow incorrect values to pass silently

Priority 3 (Medium):
- [File:Line] Could simplify logic using early returns or guard clauses

Priority 4 (Low):
- [File:Line] Minor style or documentation improvement
```

---

## Before/After Examples

**Before:**
```python
def get_user_data(id):
    return db.query("SELECT * FROM users WHERE id = " + id)
```

**After:**
```python
def get_user_data(id):
    return db.query("SELECT * FROM users WHERE id = ?", (id,))
```

---

## Severity Levels

- **Critical**: Blocks deployment, security vulnerabilities, data corruption risks
- **High**: Significant bugs, performance issues, maintainability problems
- **Medium**: Code quality issues, minor bugs, style violations
- **Low**: Minor improvements, best practice suggestions

---

## What to Avoid

- Minor stylistic preferences that do not affect functionality
- Personal coding style preferences
- Issues already handled by automated linting (Ruff, pre-commit hooks)
- Nitpicking without substantial benefit

---

## Communication Style

- Friendly and direct
- Assume good intent; avoid blaming or nitpicking
- Focus on teaching, not just correcting
- Always explain "why," not just "what"
- Professional and constructive: focus on the code, not the person
- Specific and clear: reference exact lines (`file:line`) and provide concrete examples
- Educational: explain why changes are needed
- Balanced: acknowledge good practices alongside suggestions for improvement
