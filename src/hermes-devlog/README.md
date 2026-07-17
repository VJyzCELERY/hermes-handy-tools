# Hermes Devlog Lite

`hermes-devlog` is a local, revisioned ledger for bounded Hermes workflow
coordination. It records goals, policy, worker sessions, checkpoints, review
evidence, and exact resume actions below `$HERMES_HOME/dev-log/`.

The package also installs a Hermes Agent plugin entry point. Enable the
`hermes-devlog` plugin and its `hermes-devlog` toolset in Hermes after
installation; the plugin registers the `hermes_devlog` tool without modifying
Hermes core.

The package does not call GitHub, OpenCode, tmux, Telegram, a network, a
subprocess, or a merge command. Hermes owns those external actions; this
package records their declared intent and verified outcomes.

```sh
uv run hermes-devlog activate '<schema-v2-json-payload>'
```

Schema v2 stores the root semantic goal in `config.goal` (`objective`, success
criteria, and optional approach) and materializes it in the root state node.
Subgoals live in `state.goal_graph` and carry the same semantic fields.

`permissions` is the fixed execution-authority baseline: `claim`, `implement`,
`commit`, `push`, `create_issue`, `create_pr`, `post_review`, and `merge` are
all persisted as booleans. `create_pr` requires `push`, `push` requires
`commit`, and `merge` requires `create_pr`. `policy` controls operating
conditions (`capacity`, notifications, discovered work, auto-merge, and human
merge approval); it does not grant authority. In particular, `policy.merge` is
not a schema-v2 field.

`governance` adds evolving rule provenance and constraints. Its sources pin a
reference, content hash, and snapshot reference; constraints may narrow or
explain existing controls but cannot override a `false` permission.

## Install into Hermes Agent

Install the package into the Python environment used by Hermes, then enable
the plugin and toolset:

```sh
uv pip install --python "$HOME/.hermes/hermes-agent/venv/bin/python" .
hermes plugins enable hermes-devlog
hermes tools enable hermes-devlog
```

Install the bundled replacement skill into the active Hermes home and start a
new Hermes session so plugin and skill discovery run again:

```sh
install -d "$HOME/.hermes/skills/hermes-development-log"
install skills/hermes-development-log.md \
  "$HOME/.hermes/skills/hermes-development-log/SKILL.md"
hermes doctor
hermes tools list
```

For a profile-specific installation, replace `$HOME/.hermes` with that
profile's `HERMES_HOME` in both commands and run Hermes with the matching
profile.

Later `amend_config` and `amend_state` operations require a non-empty reason
and `expected_revision`, validate the complete
resulting schema and semantics, and accept optional secret-free JSON-object
`extra` metadata. Historical phase runs retain their route after route amendments.

Each revision is an immutable hash-linked JSON event at
`audit/events/<revision>.json`, with `audit/HEAD.json`. Use bounded latest-first
`audit_list` (maximum 100) returns compact summaries; `audit_show` returns an
event snapshot. `audit_repair` requires a reason and records a new revision.

Sensitive questions are escalated with `question` and resumed through the
`resolve_question` operation. Completed goals are terminal and reject further
state mutations.
