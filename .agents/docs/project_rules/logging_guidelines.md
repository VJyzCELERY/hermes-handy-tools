# Logging Guidelines

## Overview
These rules enforce consistent and effective logging practices across the MAIN-PROJECT and its subprojects.

---

## General Rules
1. **Avoid Using `print()`**:
   - Debugging and messaging must be achieved using Python’s `logging` library.
   - The use of `print()` is discouraged except for CLI-specific tools.

2. **Log Levels**:
   - Use appropriate log levels for different scenarios:
     - `DEBUG`: Development diagnostics or detailed logs.
     - `INFO`: High-level process execution summaries.
     - `WARNING`: Alerts about non-critical issues.
     - `ERROR`: Critical errors and failures.

---

## Logger Configuration

### Example Logger Setup
Below is an example demonstrating how to configure and use a centralized logger across your subproject:

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Example usage
if __name__ == "__main__":
    logger.info("Subproject started successfully.")
    try:
        value = 10 / 2
        logger.debug("Value calculated: %s", value)
    except ZeroDivisionError as e:
        logger.error("Calculation failed.", exc_info=True)
```
All loggers must:
- Be instantiated using Python's `logging` module.
- Follow this setup template:

```python
import logging

def setup_logger(name, log_file="app.log", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
```

---

## Subproject-Specific Rules
Subprojects extend these rules and define additional configurations if required:
- Custom log outputs per service.
- Additional logging integrations (e.g., external log streams).