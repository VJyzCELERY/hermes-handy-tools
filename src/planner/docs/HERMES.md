# Hermes Integration

## Overview

Planner integrates with Hermes Agent through:
1. **Skill** — instructions for LLM on how to use the CLI
2. **Orchestrator/Worker roles** — enforced by the system
3. **Custom tools** — optional native Hermes tools wrapping the CLI
4. **Background execution** — subagents for autonomous task execution

## Skill Installation

```bash
planner install-skill
```

Copies `skill/SKILL.md` to `~/.hermes/skills/planner/SKILL.md`.

After installation, Hermes can load it:

```
skill_view(name='planner')
```

## Orchestrator Mode

**Trigger**: "orchestrate `<project>`"

### Flow

```
1. planner status --project <name>
2. Report state to user
3. Wait for go-ahead
4. planner dispatch --project <name> --profile <profile>
5. delegate_task to worker subagent
6. Wait for completion (background + notify_on_complete)
7. planner verify --project <name> --task-id <id>
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
1. skill_view(name='planner')
2. planner dispatch --project <name>
3. Execute the task (follow body instructions)
4. planner task complete --result "<summary>"
5. planner task log --message "Completed"
6. STOP
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
1. Load skill: skill_view(name='planner')
2. Run: planner dispatch --project <project>
3. Execute the active task (ONE task only)
4. Run: planner task complete --result "<summary>"
5. STOP. Do NOT execute the next task.

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

## Custom Hermes Tools (Optional)

Register as a native Hermes tool:

```python
# ~/.hermes/hermes-agent/tools/planner.py
from hermes_agent.tools import registry

@registry.register("planner")
def planner_tool(action: str, **kwargs):
    """Task planner operations."""
    import subprocess
    cmd = ["planner", action] + [f"--{k}={v}" for k, v in kwargs.items()]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {"output": result.stdout, "error": result.stderr, "code": result.returncode}
```

## Migration from Development-Log

1. **Phase 1**: Parallel running — both systems coexist
2. **Phase 2**: Import — `planner import --from-devlog <project> --project <name>`
3. **Phase 3**: Switch over — update skill to use Planner CLI
4. **Phase 4**: Deprecate old scripts
