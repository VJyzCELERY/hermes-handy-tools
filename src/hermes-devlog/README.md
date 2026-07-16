# Hermes Devlog Lite

`hermes-devlog` is a local, revisioned ledger for bounded Hermes workflow
coordination. It records goals, policy, worker sessions, checkpoints, review
evidence, and exact resume actions below `$HERMES_HOME/dev-log/`.

The package does not call GitHub, OpenCode, tmux, Telegram, a network, a
subprocess, or a merge command. Hermes owns those external actions; this
package records their declared intent and verified outcomes.

```sh
uv run hermes-devlog activate '{"goal_id":"demo","title":"Demo","template":{"release":"v1","commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","manifest_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","snapshot":"snapshots/demo"},"profile":{"name":"native","match":"native","sources":[]},"route":{"model":"openai/gpt-5.6-luna","variant":"high"},"permissions":{"implement":true,"merge":false}}'
```

All mutation commands require an explicit `expected_revision`; stale writers
receive a structured error and cannot overwrite valid state.
