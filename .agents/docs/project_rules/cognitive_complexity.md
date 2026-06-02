# Cognitive Complexity Guidelines

## Overview
Cognitive complexity measures how difficult code is to understand. Unlike cyclomatic complexity (which counts execution paths), cognitive complexity accounts for nesting, breaks in linear flow, and human readability. Keeping cognitive complexity low ensures code stays clean, maintainable, and reviewable.

---

## Threshold
- **Maximum cognitive complexity per function: 15**
- Functions exceeding this threshold must be refactored before merging.

---

## Tools

### 1. Ruff (C901 - McCabe Complexity)
Ruff enforces complexity at lint time via the `C901` rule. This is included in the `pyproject.toml` configuration for every subproject:

```toml
[tool.ruff]
select = ["E", "W", "F", "D", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 15
```

Running the linter will flag any function that exceeds the threshold:
```bash
make lint
```

### 2. Radon (Detailed Complexity Reports)
Radon provides granular cyclomatic complexity analysis and maintainability index reporting beyond what Ruff offers. Use it for deeper audits.

Radon is included in the `dev` dependency group. To add it to a new subproject:

```bash
uv add --dev radon
```

#### Usage
```bash
# Cyclomatic complexity report, show only C grade and below
uv run radon cc . -a -nc

# Maintainability index, show only B grade and below
uv run radon mi . -n B
```

A dedicated Makefile target is available:
```bash
make complexity
```

#### Complexity Grades (Radon)
| Grade | Score | Meaning                        |
|-------|-------|--------------------------------|
| A     | 1-5   | Simple, low risk               |
| B     | 6-10  | Well-structured, moderate risk |
| C     | 11-15 | Slightly complex, tolerable    |
| D     | 16-20 | High complexity — refactor     |
| E     | 21-30 | Very high — must refactor      |
| F     | 31+   | Unmaintainable                 |

**Target**: All functions must be grade **C or better** (score <= 15).

---

## How to Reduce Complexity

### 1. Extract Functions
Break large functions into smaller, focused units:

```python
# Bad - deeply nested, high complexity
def process_order(order):
    if order.is_valid:
        if order.has_items:
            for item in order.items:
                if item.in_stock:
                    reserve_stock(item)
                    charge_customer(order, item)

# Good - each function has a single responsibility
def process_order(order):
    if not order.is_valid or not order.has_items:
        return
    process_items(order.items)

def process_items(items):
    for item in items:
        if item.in_stock:
            fulfill_item(item)
```

### 2. Use Early Returns (Guard Clauses)
Reduce nesting by handling edge cases first:

```python
# Bad - deeply nested
def get_discount(user):
    if user:
        if user.is_premium:
            if user.years > 5:
                return 0.3
            else:
                return 0.15
        else:
            return 0.05
    return 0

# Good - flat structure with guard clauses
def get_discount(user):
    if not user:
        return 0
    if not user.is_premium:
        return 0.05
    if user.years > 5:
        return 0.3
    return 0.15
```

### 3. Replace Conditionals with Lookup Tables
```python
# Bad - long if/elif chain
def get_price(tier):
    if tier == "basic":
        return 10
    elif tier == "standard":
        return 20
    elif tier == "premium":
        return 30
    return 0

# Good - lookup table
TIER_PRICES = {"basic": 10, "standard": 20, "premium": 30}

def get_price(tier):
    return TIER_PRICES.get(tier, 0)
```

### 4. Simplify Boolean Expressions
```python
# Bad - double negation, hard to read
if not (not is_active or not has_permission):
    do_something()

# Good - clear and direct
if is_active and has_permission:
    do_something()
```

---

## Enforcement Summary

| Tool    | When it runs     | What it checks                        | Command          |
|---------|------------------|---------------------------------------|------------------|
| Ruff C901 | `make lint`    | Max complexity per function           | `make lint`      |
| Radon   | `make complexity`| Detailed grades + maintainability index | `make complexity` |

Both must pass cleanly before code is merged.
