# Hermes Integration

## Overview

Planner integrates with Hermes Agent through:
1. **Custom tool** — native Hermes tool wrapping the CLI (primary)
2. **Skill** — fallback instructions for LLM on how to use the CLI
3. **Orchestrator/Worker roles** — enforced by the system
4. **Background execution** — subagents for autonomous task execution

## Custom Tool (Primary)

The planner registers as a native Hermes tool at `~/.hermes/hermes-agent/tools/planner_tool.py`.

### How it works

The tool wraps the planner CLI via subprocess calls. When Hermes calls the `planner` tool, the handler:
1. Maps `action` + `args` to CLI arguments
2. Runs `planner <subcommand> --json` via subprocess
3. Returns parsed JSON output

### Installation

```bash
# 1. Install the planner CLI
cd src/planner
uv sync          # or: pip install -e .

# 2. Set PLANNER_DIR (for uv-based invocation)
export PLANNER_DIR="$(pwd)"

# 3. Copy the tool file (already done if you're reading this)
cp ~/.hermes/hermes-agent/tools/planner_tool.py ~/.hermes/hermes-agent/tools/

# 4. Restart Hermes (/reset)
```

### Configuration

| Env Var | Purpose | Default |
|---------|---------|---------|
| `PLANNER_DIR` | Path to planner project root | Falls back to PATH lookup |

If `PLANNER_DIR` is set, the tool uses `uv run --directory $PLANNER_DIR planner` to invoke the CLI. Otherwise, it looks for `planner` on PATH.

### Tool Schema

Single tool with two parameters:

```
planner(action: str, args?: dict)
```

**Actions:**

| Category | Actions |
|----------|---------|
| Project | `project_create`, `project_list`, `project_show`, `project_archive` |
| Goal | `goal_add`, `goal_list`, `goal_complete` |
| Task | `task_add`, `task_list`, `task_show`, `task_activate`, `task_complete`, `task_block`, `task_cancel`, `task_delete`, `task_edit`, `task_log`, `task_search`, `task_prioritize`, `task_move` |
| Deps | `dep_add`, `dep_remove`, `dep_list` |
| Workflow | `status`, `dispatch` |

### Example Calls

```python
# Create a project
planner(action="project_create", args={"name": "my-project", "description": "..."})

# Add a task
planner(action="task_add", args={"project": "my-project", "title": "Step 1", "body": "..."})

# Activate next task
planner(action="task_activate", args={"project": "my-project"})

# Complete active task
planner(action="task_complete", args={"result": "Done"})

# Get project status
planner(action="status", args={"project": "my-project"})

# Dispatch next task for a worker
planner(action="dispatch", args={"project": "my-project", "profile": "worker"})
```

## Skill (Fallback)

The skill at `skill/SKILL.md` provides CLI-based instructions for Hermes. Use this when:
- The custom tool isn't installed
- You prefer CLI commands over tool calls
- You're running in an environment without the tool file

### Skill Installation

```bash
planner install-skill
```

Copies `skill/SKILL.md` to `~/.hermes/skills/planner/SKILL.md`.

## Orchestrator Mode

**Trigger**: "orchestrate `<project>`"

### Flow

```
1. planner(action="status", args={"project": "<name>"})
2. Report state to user
3. Wait for go-ahead
4. planner(action="dispatch", args={"project": "<name>", "profile": "<profile>"})
5. delegate_task to worker subagent
6. Wait for completion (background + notify_on_complete)
7. planner(action="task_complete", args={"result": "..."})
8. Notify user (Telegram)
9. Repeat
```

### Rules
- Must NOT execute tasks directly
- Must verify single-task completion before spawning next
- 1 subagent = 1 active task max
- Clean up orphaned processes after every subagent

## Worker Mode

**Trigger**: "work on `<project>`"

### Flow

```
1. planner(action="dispatch", args={"project": "<name>"})
2. Execute the task (follow body instructions)
3. planner(action="task_complete", args={"result": "<summary>"})
4. STOP
```

### Rules
- Exactly 1 task per subagent
- STOP means STOP — no continuation
- Do NOT read the planned queue
- Do NOT activate the next task

### Delegation Goal Template

```
Work on the <project> project. You are a WORKER, not an orchestrator.

STEPS (follow exactly):
1. Run: planner(action="dispatch", args={"project": "<project>"})
2. Execute the active task (ONE task only)
3. Run: planner(action="task_complete", args={"result": "<summary>"})
4. STOP. Do NOT execute the next task.

ONE TASK. THEN STOP.
```

## Profile Integration

Tasks can be assigned to specific Hermes profiles:

```bash
planner task add --project tinycua --title "Step 7" --assignee tinycua-developer
planner dispatch --project tinycua --profile tinycua-developer
```

### Multi-profile orchestration

```bash
planner dispatch --project tinycua --profile tinycua-developer  # code tasks
planner dispatch --project tinycua --profile reviewer           # review tasks
```

## Migration from Development-Log

1. **Phase 1**: Parallel running — both systems coexist
2. **Phase 2**: Import — `planner import --from-devlog <project> --project <name>`
3. **Phase 3**: Switch over — update skill to use Planner CLI
4. **Phase 4**: Deprecate old scripts
