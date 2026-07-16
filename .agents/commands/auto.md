---
description: Enables automatic mutation authorization for the current session
---

# Auto

Read root `AGENTS.md`. `/auto` enables `--auto` behavior for all commands in the
current session. Treat it as the user's explicit authorization for each
command's documented mutation batch after validation and preview. Do not
persist this setting; it ends with the session.

## Failure

- Stop on invalid input, failed validation, conflicts, unsafe paths, or active
  human discussion. `/auto` does not authorize guessing or unsafe recovery.
