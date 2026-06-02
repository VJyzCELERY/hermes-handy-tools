# Security Guidelines

## Secrets and Credentials

**Never commit secrets.** This is the most important security rule.

- Never hardcode API keys, passwords, tokens, or credentials in source code
- Never commit `.env` files that contain real credentials
- Always use `.env.example` files with placeholder values as the committed reference

**Correct pattern:**
```
# .env.example (committed to git)
DATABASE_URL=postgres://user:password@localhost:5432/mydb
API_KEY=your-api-key-here
SECRET_KEY=change-me-in-production
```

```
# .env (NOT committed — in .gitignore)
DATABASE_URL=postgres://realuser:realpassword@prod-host:5432/proddb
API_KEY=sk-live-abc123...
SECRET_KEY=super-secret-random-string
```

---

## Environment Variables

- Load all configuration from environment variables, never from hardcoded values
- Use a library like `python-dotenv` to load `.env` files locally
- Document all required environment variables in `.env.example` and in the subproject `README.md`
- Validate required environment variables at application startup — fail fast with a clear error if any are missing

```python
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
```

---

## Input Validation

- Validate all external inputs before processing: API request bodies, CLI arguments, file contents, environment variables
- Never trust user-supplied data without validation
- Use explicit type checking and value range validation
- Return clear error messages for invalid inputs without leaking internal details

```python
def create_user(email: str, age: int) -> dict:
    if not email or "@" not in email:
        raise ValueError("Invalid email address")
    if age < 0 or age > 150:
        raise ValueError("Age must be between 0 and 150")
    # ...
```

---

## Error Handling and Information Leakage

- Never expose internal stack traces or system details to end users
- Log full error details server-side; return generic error messages to callers
- Do not include sensitive data (tokens, passwords, PII) in log messages

```python
# Bad: leaks internal details
except Exception as e:
    return {"error": str(e)}  # could expose file paths, DB schema, etc.

# Good: generic user message, full detail in logs
except Exception:
    logger.exception("Unexpected error processing request for user_id=%s", user_id)
    return {"error": "An unexpected error occurred. Please try again."}
```

---

## Dependency Security

- Keep dependencies up to date
- Pin dependency versions in `pyproject.toml` to avoid supply-chain surprises
- Check for known vulnerabilities periodically:
  ```bash
  uv pip audit
  ```
- Do not add new dependencies without reviewing their maintenance status and known CVEs

---

## Code Review Security Checklist

When reviewing code for security, check:

- [ ] No hardcoded secrets or credentials
- [ ] All inputs validated and sanitized
- [ ] SQL queries use parameterized queries (no string concatenation)
- [ ] No sensitive data in log output
- [ ] Error messages do not leak internal state
- [ ] `.env` files are in `.gitignore`
- [ ] New dependencies reviewed for CVEs

---

## References

- `.agents/docs/agents/code_review.md` — full security review checklist under "Security (High Priority)"
- `.agents/docs/project_rules/logging_guidelines.md` — logging standards
