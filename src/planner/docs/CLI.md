# CLI Reference

## Global Options

```bash
planner [OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|--------|-------------|
| `--db PATH` | Database file path (default: `~/.planner/planner.db`) |
| `--project NAME` | Set default project for commands |
| `--json` | Output as JSON |
| `--quiet` | Suppress non-essential output |

## Project Commands

### `planner project create`

```bash
planner project create NAME [--description TEXT]
```

### `planner project list`

```bash
planner project list [--status active|archived]
```

### `planner project show`

```bash
planner project show NAME
```

### `planner project archive`

```bash
planner project archive NAME
```

## Goal Commands

### `planner goal add`

```bash
planner goal add --project PROJECT --title TITLE [--description TEXT]
```

### `planner goal list`

```bash
planner goal list --project PROJECT [--status active|completed|abandoned]
```

### `planner goal complete`

```bash
planner goal complete GOAL_ID [--result TEXT]
```

### `planner goal show`

```bash
planner goal show GOAL_ID
```

## Task Commands

### `planner task add`

```bash
planner task add --project PROJECT --title TITLE [--body TEXT] [--priority N] [--assignee PROFILE] [--goal GOAL_ID] [--tag TAG] [--after DEPENDS_ON_ID]
```

### `planner task activate`

```bash
planner task activate --project PROJECT [--task-id ID]
```

Auto-picks next ready task, or activates a specific one.

### `planner task complete`

```bash
planner task complete [--result TEXT]
```

### `planner task block`

```bash
planner task block --reason TEXT
```

### `planner task cancel`

```bash
planner task cancel [--reason TEXT]
```

### `planner task log`

```bash
planner task log --message TEXT
```

### `planner task list`

```bash
planner task list --project PROJECT [--status planned|active|completed|blocked|cancelled] [--limit N] [--offset N] [--assignee PROFILE]
```

### `planner task show`

```bash
planner task show TASK_ID
```

### `planner task edit`

```bash
planner task edit TASK_ID [--title TEXT] [--body TEXT] [--priority N] [--assignee PROFILE]
```

### `planner task search`

```bash
planner task search --project PROJECT --query TEXT
```

### `planner task delete`

```bash
planner task delete TASK_ID
```

Only planned tasks.

## Dependency Commands

### `planner task dep add`

```bash
planner task dep add TASK_ID --depends-on DEP_ID
```

### `planner task dep remove`

```bash
planner task dep remove TASK_ID --depends-on DEP_ID
```

### `planner task dep list`

```bash
planner task dep list TASK_ID
```

### `planner task dep graph`

```bash
planner task dep graph --project PROJECT
```

## Organization Commands

### `planner task move`

```bash
planner task move TASK_ID --position N
```

### `planner task prioritize`

```bash
planner task prioritize TASK_ID
```

## Orchestration Commands

### `planner status`

```bash
planner status --project PROJECT
```

### `planner dispatch`

```bash
planner dispatch --project PROJECT [--profile PROFILE]
```

### `planner verify`

```bash
planner verify --project PROJECT --task-id ID
```

## Web UI Commands

### `planner web`

```bash
planner web [--host HOST] [--port PORT] [--reload]
```

## Skill Installation

### `planner install-skill`

```bash
planner install-skill [--path PATH]
```

Copies `skill/SKILL.md` to `~/.hermes/skills/planner/SKILL.md`.

## JSON Output

All commands support `--json` for machine-readable output.
