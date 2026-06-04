# HITL Command Design v4 — opencode-tool

## Depends On

Profile system (env-design.md v4).
HITL behavior depends on current profile's mode:

  - isolated mode: REST API + TUI fallback (full capabilities)
  - collaborate mode: REST API only (safe, no TUI conflicts)

## Problem

The REST API (`/permission`, `/question`) has blind spots:
- `/question` returns stale or empty data in v1.15.7+
- Some HITL states are only observable through TUI state
- Our current workaround (scanning messages) is fragile

## Mode-Aware Detection

### isolated mode (default)

  Layer 1: REST API (permissions + questions) — fast
  Layer 2: Message scanning (last assistant message) — moderate
  Layer 3: TUI control/next (safe — no competition) — slow

### collaborate mode

  Layer 1: REST API (permissions + questions) — fast
  Layer 2: Message scanning (last assistant message) — moderate
  DONE — no Layer 3 (would conflict with user's TUI)

If both layers fail in collaborate mode:
  → Report "TUI required — switch to isolated mode or handle manually"

## Commands

### hitl detect

```bash
opencode-tool hitl detect <session_id> [--json] [--wait] [--timeout 5]
```

  --wait: Block until HITL found (isolated mode only, uses Layer 3)
  --timeout: Seconds to wait (default 5)

Detection flow:
  1. Get current profile mode
  2. Layer 1: REST API (_get_session_info)
  3. Layer 2: Message scan (_scan_session_questions)
  4. If mode=isolated AND --wait AND nothing found: Layer 3
  5. Return result with source indicator

Output (human-readable):
```
Session: ses_abc123
Profile: myproject (isolated)
Source:  message-scan
Type:    question

  Q1: Confirm Action
      The agent wants to run: rm -rf /tmp/old
      Options:
        1. yes: Allow this action
        2. no:  Reject this action
```

Output (JSON):
```json
{
  "session_id": "ses_abc123",
  "profile": "myproject",
  "mode": "isolated",
  "type": "question",
  "source": "message-scan",
  "requests": [...]
}
```

### hitl respond

```bash
opencode-tool hitl respond <session_id> <answer> [--json]
```

Auto-detects type from pending request:
  - question → answer is label or text
  - permission → answer is once | always | reject

Response flow:
  1. Detect type (same as detect)
  2. Layer 1: REST API reply
  3. Layer 2: Message part patch
  4. If mode=isolated AND layers 1-2 fail: Layer 3 (TUI)
  5. Report which layer handled it

### hitl dismiss

```bash
opencode-tool hitl dismiss <session_id> [--json]
```

  1. REST API: POST /session/{id}/abort
  2. If mode=isolated: TUI execute-command session.interrupt
  3. Report source

## Implementation

### api.py additions

```python
# TUI methods (safe — publish events, no consumption)

def tui_execute_command(self, command: str) -> bool:
    return self._post("/tui/execute-command", {"command": command})

def tui_publish(self, event_type: str, properties: dict) -> bool:
    return self._post("/tui/publish", {"type": event_type, "properties": properties})

def tui_show_toast(self, message: str, title: str = None,
                   variant: str = "info") -> bool:
    data = {"message": message, "variant": variant}
    if title:
        data["title"] = title
    return self._post("/tui/show-toast", data)

def tui_control_next(self, timeout: int = 5) -> Optional[dict]:
    """Long-poll for control request (isolated mode only)."""
    try:
        resp = requests.get(
            f"{self.base_url}/tui/control/next",
            auth=self.auth,
            timeout=timeout
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if data else None
        return None
    except:
        return None

def tui_control_response(self, body: any) -> bool:
    return self._post("/tui/control/response", {"body": body})
```

### hitl.py core logic

```python
"""HITL management commands."""

import os
import click
from rich.console import Console
from ..api import OpenCodeAPI

console = Console()

def _get_mode() -> str:
    """Get current profile mode."""
    return os.environ.get("OPENCODE_SERVER_MODE", "isolated")

def _detect_rest(api, session_id):
    """Layer 1: REST API detection."""
    from ..commands.session import _get_session_info
    info = _get_session_info(api, session_id)
    if info and (info["permissions"] or info["question_blocked"]):
        return info, "rest-api"
    return None, None

def _detect_messages(api, session_id):
    """Layer 2: Message scanning."""
    from ..commands.question import _scan_session_questions
    questions = _scan_session_questions(api, session_id)
    if questions:
        return {"question_blocked": True, "question_data": questions}, "message-scan"
    return None, None

def _detect_tui(api, timeout=5):
    """Layer 3: TUI control/next (isolated only)."""
    request = api.tui_control_next(timeout=timeout)
    if request:
        return request, "tui-control"
    return None, None

def _detect_all(api, session_id, mode, wait=False, timeout=5):
    """Run all detection layers."""
    # Layer 1
    result, source = _detect_rest(api, session_id)
    if result:
        return result, source

    # Layer 2
    result, source = _detect_messages(api, session_id)
    if result:
        return result, source

    # Layer 3 (isolated only, with --wait)
    if wait and mode == "isolated":
        result, source = _detect_tui(api, timeout)
        if result:
            return result, source

    return None, None

def _respond_permission(api, session_id, answer, mode, json_out):
    """Respond to a permission request."""
    permissions = api.get_permissions()
    session_perms = [p for p in permissions if p.get("sessionID") == session_id]

    if not session_perms:
        console.print("[yellow]No pending permissions[/yellow]")
        return

    for p in session_perms:
        pid = p.get("id")
        if pid:
            api.reply_permission(pid, answer)

    if json_out:
        import json
        print(json.dumps({"session_id": session_id, "responded": True, "source": "rest-api"}))
    else:
        console.print(f"[green]Granted: {answer}[/green]")

def _respond_question(api, session_id, answer, result, mode, json_out):
    """Respond to a question request."""
    from ..commands.question import _find_question_by_id, _scan_session_questions

    # Find question ID
    questions = _scan_session_questions(api, session_id)
    if not questions:
        console.print("[yellow]No pending questions[/yellow]")
        return

    q = questions[0]
    qid = q.get("id")

    # Try REST API reply
    try:
        all_questions = api.get_questions()
        match = next((aq for aq in all_questions if aq.get("tool", {}).get("callID") == qid), None)
        if match:
            request_id = match.get("id")
            answers_array = [[answer]]
            api.reply_question(request_id, answers_array)

            if json_out:
                import json
                print(json.dumps({"session_id": session_id, "responded": True, "source": "rest-api"}))
            else:
                console.print(f"[green]Replied: {answer}[/green]")
            return
    except:
        pass

    # TUI fallback (isolated only)
    if mode == "isolated":
        api.tui_execute_command("session.interrupt")
        if json_out:
            import json
            print(json.dumps({"session_id": session_id, "dismissed": True, "source": "tui"}))
        else:
            console.print(f"[yellow]Question not replyable via API — interrupted session via TUI[/yellow]")
    else:
        console.print("[red]Cannot reply — question not registered in API[/red]")
        console.print("  Hint: switch to isolated mode or handle manually in TUI")


@click.group()
def hitl():
    """Manage Human-In-The-Loop requests."""
    pass

@hitl.command("detect")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True)
@click.option("--wait", is_flag=True, help="Block until HITL found (isolated only)")
@click.option("--timeout", default=5, help="Wait timeout in seconds")
def detect(session_id, json_out, wait, timeout):
    """Detect pending HITL requests for a session."""
    api = OpenCodeAPI()
    mode = _get_mode()
    profile = os.environ.get("OPENCODE_TOOL_PROFILE", "auto")

    result, source = _detect_all(api, session_id, mode, wait, timeout)

    if json_out:
        import json
        print(json.dumps({
            "session_id": session_id,
            "profile": profile,
            "mode": mode,
            "type": _get_hitl_type(result),
            "source": source,
            "data": result
        }, indent=2))
        return

    if not result:
        console.print("[green]No pending HITL requests[/green]")
        return

    console.print(f"Session: [cyan]{session_id}[/cyan]")
    console.print(f"Profile: [yellow]{profile}[/yellow] ({mode})")
    console.print(f"Source:  [dim]{source}[/dim]")
    console.print(f"Type:    [bold]{_get_hitl_type(result)}[/bold]")
    console.print()
    _print_hitl_details(result)

@hitl.command("respond")
@click.argument("session_id")
@click.argument("answer")
@click.option("--json", "json_out", is_flag=True)
def respond(session_id, answer, json_out):
    """Respond to a pending HITL request."""
    api = OpenCodeAPI()
    mode = _get_mode()

    result, _ = _detect_all(api, session_id, mode)
    hitl_type = _get_hitl_type(result)

    if hitl_type == "permission":
        _respond_permission(api, session_id, answer, mode, json_out)
    elif hitl_type == "question":
        _respond_question(api, session_id, answer, result, mode, json_out)
    else:
        console.print("[yellow]No pending HITL request found[/yellow]")

@hitl.command("dismiss")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True)
def dismiss(session_id, json_out):
    """Dismiss all pending HITL requests (stops agent)."""
    api = OpenCodeAPI()
    mode = _get_mode()

    if api.abort_session(session_id):
        source = "rest-api"
    elif mode == "isolated":
        api.tui_execute_command("session.interrupt")
        source = "tui"
    else:
        console.print("[red]Failed to dismiss[/red]")
        raise SystemExit(1)

    if json_out:
        import json
        print(json.dumps({"session_id": session_id, "dismissed": True, "source": source}))
    else:
        console.print(f"[green]Dismissed: {session_id}[/green]")
```

## File Structure

```
opencode_tool/
├── commands/
│   ├── hitl.py          # NEW: hitl detect/respond/dismiss
│   ├── profile.py       # NEW: profile set/create/list/delete/current
│   ├── server.py        # ENHANCED: start/stop with port detection
│   ├── session.py       # existing
│   ├── permission.py    # existing
│   ├── question.py      # existing
│   └── ...
├── api.py               # ADD: TUI fallback methods
├── config.py            # ENHANCED: new config keys
├── registry.py          # NEW: server registry + port detection
└── main.py              # UPDATE: register new commands
```

## Testing with uv

```bash
cd src/opencode-tool

# Install with dev deps
uv pip install -e ".[dev]" --system

# Run tests
uv run pytest tests/ -v

# Specific test
uv run pytest tests/unit/test_hitl.py -v

# Lint
uv run ruff check .
uv run ruff format .
```
