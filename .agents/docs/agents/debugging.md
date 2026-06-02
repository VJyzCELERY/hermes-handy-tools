# Debugging Guide

## General Debugging Workflow

1. **Reproduce first**: Confirm the issue is reproducible with a minimal case
2. **Check logs**: Look at application logs before adding debug statements
3. **Isolate**: Narrow down which module, function, or layer is the source
4. **Verify assumptions**: Use assertions or temporary logging to confirm intermediate values
5. **Fix and verify**: After fixing, run `make test` to confirm no regressions

---

## Log File Locations

By default, Python applications built from this template write logs to:

```
src/my-subproject/logs/application.log
```

Check `.agents/docs/project_rules/logging_guidelines.md` for the configured log level and format.

---

## Useful Log Grep Patterns

Search for errors and exceptions:
```bash
grep -i "error\|exception\|failed\|traceback" logs/application.log | tail -30
```

Search for a specific entity or ID:
```bash
grep "user_id=abc123" logs/application.log | tail -20
```

Search for warnings:
```bash
grep -i "warning\|warn" logs/application.log | tail -20
```

Follow logs in real-time:
```bash
tail -f logs/application.log
```

---

## Debugging Python Code

### Use `logging` not `print()`

Always debug via the logging module — `print()` is banned in non-CLI code:

```python
import logging

logger = logging.getLogger(__name__)

def process_payment(order_id: str) -> dict:
    logger.debug("Processing payment for order_id=%s", order_id)
    # ...
    logger.info("Payment processed successfully for order_id=%s", order_id)
```

Set log level to `DEBUG` temporarily during debugging:
```python
logging.basicConfig(level=logging.DEBUG)
```

### Isolate with pytest

Run a single failing test to isolate the issue:
```bash
uv run pytest tests/unit/test_payment.py::test_raises_on_invalid_order -v
```

Run with full output (no capture):
```bash
uv run pytest tests/ -s -v
```

### Check for Common Issues

**Import errors:**
```bash
uv run python -c "from my_subproject.service import PaymentService"
```

**Dependency issues:**
```bash
uv pip list | grep <package-name>
```

**Ruff violations causing unexpected behavior:**
```bash
make lint
```

**Complexity violations:**
```bash
make complexity
```

---

## Debugging Tests

If `make test` fails unexpectedly:

1. Run with `-s` to see all stdout/stderr output:
   ```bash
   uv run pytest tests/ -s
   ```

2. Run with `-x` to stop at first failure:
   ```bash
   uv run pytest tests/ -x -v
   ```

3. Print a specific variable inside a test using `capsys`:
   ```python
   def test_something(capsys):
       result = my_function()
       captured = capsys.readouterr()
       print(captured.out)  # only in tests
   ```

---

## Common Root Causes

| Symptom | Likely Cause |
|---------|-------------|
| `ModuleNotFoundError` | Wrong virtualenv, missing install, relative import |
| `AttributeError: NoneType` | Function returned `None` unexpectedly, missing null check |
| `KeyError` | Dict key assumption wrong, use `.get()` with a default |
| Test passes locally, fails in CI | Environment variable missing, hardcoded path, OS difference |
| Coverage drops below 80% | New code added without corresponding tests |
| Ruff lint fails after auto-fix | Manual intervention needed for non-auto-fixable rules |

---

## References

- `.agents/docs/project_rules/logging_guidelines.md` — logging configuration and standards
- `.agents/docs/agents/testing.md` — test organization and debugging tests
