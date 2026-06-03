"""Session management commands."""

import json
import time
from typing import Optional

import click
import requests
from rich.console import Console
from rich.table import Table

from ..api import OpenCodeAPI

console = Console()


@click.group()
def session():
    """Manage OpenCode sessions."""
    pass


@session.command("list")
@click.option("--limit", "-n", default=20, help="Number of sessions to show")
@click.option("--offset", default=0, help="Offset for pagination")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
@click.option("--filter", "filter_status", multiple=True, type=click.Choice([
    "all", "busy", "active", "blocked", "idle",
    "permission-block", "question-block", "retry"
]), help="Filter by session status (can specify multiple)")
def list_sessions(limit: int, offset: int, json_out: bool, filter_status: tuple):
    """List all sessions with pagination and optional status filter."""
    api = OpenCodeAPI()
    
    try:
        sessions = api.get_sessions()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    
    # Default to "all" if no filter specified
    if not filter_status:
        filter_status = ("all",)
    
    # Get status for each session if filtering
    if filter_status != ("all",):
        filtered = []
        seen_ids = set()
        
        for s in sessions:
            sid = s.get("id")
            if not sid or sid in seen_ids:
                continue
            
            info = _get_session_info(api, sid)
            if info is None:
                continue
            
            status = info["status"]
            has_permissions = bool(info["permissions"])
            has_questions = info["question_blocked"]
            
            # Check if session matches ANY of the filters (OR logic)
            matches = False
            for f in filter_status:
                if f == "busy" and status == "busy" and not has_permissions and not has_questions:
                    matches = True
                elif f == "active" and (status == "busy" or has_permissions or has_questions or status == "retry"):
                    matches = True
                elif f == "blocked" and (has_permissions or has_questions or status == "retry"):
                    matches = True
                elif f == "idle" and status == "idle":
                    matches = True
                elif f == "permission-block" and has_permissions:
                    matches = True
                elif f == "question-block" and has_questions:
                    matches = True
                elif f == "retry" and status == "retry":
                    matches = True
                
                if matches:
                    break
            
            if matches:
                filtered.append(s)
                seen_ids.add(sid)
        
        sessions = filtered
    
    # Sort by updated time (newest first)
    sessions.sort(key=lambda s: s.get("time", {}).get("updated", 0), reverse=True)
    
    # Apply pagination
    total = len(sessions)
    sessions = sessions[offset:offset + limit]
    
    filter_display = ",".join(filter_status) if filter_status else "all"
    
    if json_out:
        print(json.dumps({
            "sessions": sessions,
            "total": total,
            "offset": offset,
            "limit": limit,
            "filter": filter_display
        }, indent=2))
        return
    
    if not sessions:
        console.print(f"[yellow]no sessions found (filter: {filter_display})[/yellow]")
        return
    
    table = Table(title=f"Sessions (filter: {filter_display}, showing {offset + 1}-{min(offset + limit, total)} of {total})")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Agent", style="yellow")
    table.add_column("Model", style="magenta")
    table.add_column("Updated", style="blue")
    
    for s in sessions:
        sid = s.get("id", "?")
        title = s.get("title", "untitled")[:40]
        agent = s.get("agent", "?")
        model = s.get("model", {})
        model_id = model.get("id", "?") if isinstance(model, dict) else "?"
        updated = s.get("time", {}).get("updated", 0)
        
        if updated:
            from datetime import datetime
            updated_str = datetime.fromtimestamp(updated / 1000).strftime("%Y-%m-%d %H:%M")
        else:
            updated_str = "?"
        
        table.add_row(sid, title, agent, model_id, updated_str)
    
    console.print(table)
    
    if total > offset + limit:
        console.print(f"\n[dim]More sessions available. Use --offset {offset + limit} to see next page.[/dim]")


@session.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def search_sessions(query: str, limit: int, json_out: bool):
    """Search sessions by title, agent, or model."""
    api = OpenCodeAPI()
    
    try:
        sessions = api.get_sessions()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    
    query_lower = query.lower()
    results = []
    
    for s in sessions:
        title = s.get("title", "").lower()
        agent = s.get("agent", "").lower()
        model = s.get("model", {})
        model_id = model.get("id", "").lower() if isinstance(model, dict) else ""
        sid = s.get("id", "").lower()
        
        if (query_lower in title or 
            query_lower in agent or 
            query_lower in model_id or
            query_lower in sid):
            results.append(s)
    
    # Sort by updated time (newest first)
    results.sort(key=lambda s: s.get("time", {}).get("updated", 0), reverse=True)
    results = results[:limit]
    
    if json_out:
        print(json.dumps(results, indent=2))
        return
    
    if not results:
        console.print(f"[yellow]no sessions matching '{query}'[/yellow]")
        return
    
    console.print(f"Found {len(results)} session(s) matching '{query}':\n")
    
    for s in results:
        sid = s.get("id", "?")
        title = s.get("title", "untitled")
        agent = s.get("agent", "?")
        model = s.get("model", {})
        model_id = model.get("id", "?") if isinstance(model, dict) else "?"
        updated = s.get("time", {}).get("updated", 0)
        
        if updated:
            from datetime import datetime
            updated_str = datetime.fromtimestamp(updated / 1000).strftime("%Y-%m-%d %H:%M")
        else:
            updated_str = "?"
        
        console.print(f"[cyan]{sid}[/cyan]")
        console.print(f"  Title: {title}")
        console.print(f"  Agent: {agent} | Model: {model_id}")
        console.print(f"  Updated: {updated_str}")
        console.print()


def _show_last_response(api: OpenCodeAPI, session_id: str, json_out: bool, hide_tools: bool):
    """Show the last assistant response from a session."""
    try:
        messages = api.get_session_messages(session_id)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    
    # Find the last assistant message
    last_assistant = None
    for msg in reversed(messages):
        info = msg.get("info", {})
        if info.get("role") == "assistant":
            last_assistant = msg
            break
    
    if not last_assistant:
        console.print("[yellow]No assistant response found[/yellow]")
        return
    
    parts = last_assistant.get("parts", [])
    
    if json_out:
        # Filter parts if hide_tools
        if hide_tools:
            parts = [p for p in parts if p.get("type") == "text"]
        print(json.dumps({
            "session_id": session_id,
            "response": parts
        }, indent=2))
        return
    
    console.print(f"Last response from [cyan]{session_id}[/cyan]:\n")
    
    for part in parts:
        ptype = part.get("type", "?")
        
        if ptype == "text":
            text = part.get("text", "")
            console.print(text)
        elif ptype == "tool":
            if not hide_tools:
                tool_name = part.get("tool", "?")
                state = part.get("state", {})
                status = state.get("status", "?")
                console.print(f"[dim]tool: {tool_name} ({status})[/dim]")
        elif ptype == "tool-call":
            if not hide_tools:
                tool_name = part.get("name", "?")
                console.print(f"[dim]tool-call: {tool_name}[/dim]")
        elif ptype == "tool-result":
            if not hide_tools:
                result = part.get("result", "")
                if isinstance(result, str) and len(result) > 200:
                    result = result[:200] + "..."
                console.print(f"[dim]tool-result: {result}[/dim]")


@session.command("get")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
@click.option("--messages", "-m", is_flag=True, help="Include messages")
@click.option("--response", "-r", is_flag=True, help="Show only the last assistant response")
@click.option("--hide-tools", is_flag=True, help="Hide tool calls in response (with --response)")
def get_session(session_id: str, json_out: bool, messages: bool, response: bool, hide_tools: bool):
    """Get session details."""
    api = OpenCodeAPI()
    
    try:
        session = api.get_session(session_id)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    
    # Handle --response flag
    if response:
        _show_last_response(api, session_id, json_out, hide_tools)
        return
    
    if json_out:
        output = session
        if messages:
            output["messages"] = api.get_session_messages(session_id)
        print(json.dumps(output, indent=2))
        return
    
    console.print(f"Session: [cyan]{session.get('id', '?')}[/cyan]")
    console.print(f"Title:   {session.get('title', 'untitled')}")
    console.print(f"Agent:   {session.get('agent', '?')}")
    
    model = session.get("model", {})
    if isinstance(model, dict):
        console.print(f"Model:   {model.get('id', '?')} ({model.get('providerID', '?')})")
        if model.get("variant"):
            console.print(f"Variant: {model.get('variant')}")
    
    time_info = session.get("time", {})
    if time_info.get("created"):
        from datetime import datetime
        created = datetime.fromtimestamp(time_info["created"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"Created: {created}")
    if time_info.get("updated"):
        from datetime import datetime
        updated = datetime.fromtimestamp(time_info["updated"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"Updated: {updated}")
    
    cost = session.get("cost", 0)
    if cost:
        console.print(f"Cost:    ${cost:.4f}")
    
    tokens = session.get("tokens", {})
    if tokens:
        console.print(f"Tokens:  {tokens.get('input', 0)} in / {tokens.get('output', 0)} out")


@session.command("status")
@click.argument("session_id", required=False)
@click.option("--monitor", is_flag=True, help="Monitor until blocked/idle")
@click.option("--interval", default=10, help="Monitor interval in seconds")
def status(session_id: str, monitor: bool, interval: int):
    """Check session status."""
    api = OpenCodeAPI()
    
    if monitor and session_id:
        _monitor_session(api, session_id, interval)
    elif session_id:
        _check_session(api, session_id)
    else:
        console.print("[red]Error: session_id required[/red]")
        raise SystemExit(1)


def _check_session(api: OpenCodeAPI, session_id: str):
    """Check session status once."""
    info = _get_session_info(api, session_id)
    if info is None:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise SystemExit(1)
    
    _print_session_info(info)


def _get_session_info(api: OpenCodeAPI, session_id: str) -> Optional[dict]:
    """Get full session info."""
    import time
    
    # Check session status from API
    statuses = api.get_session_status()
    status = statuses.get(session_id)
    
    if status is not None:
        # API provided status
        status_type = status.get("type", "unknown")
        status_detail = status
    else:
        # API returned empty — infer status from session data
        try:
            session = api.get_session(session_id)
            if not session:
                return None
            
            # Check for pending permissions
            permissions = api.get_permissions()
            session_perms = [p for p in permissions if p.get("sessionID") == session_id]
            if session_perms:
                status_type = "busy"
                status_detail = {"type": "busy", "reason": "permission_pending"}
            else:
                # Check for pending questions
                question_blocked = _check_question_blocked(api, session_id)
                if question_blocked is not None:
                    status_type = "busy"
                    status_detail = {"type": "busy", "reason": "question_pending"}
                else:
                    # Check for running tool calls (bash, edit, patch, etc.)
                    running_tools = _check_running_tools(api, session_id)
                    if running_tools:
                        tool_names = [t.get("tool", "?") for t in running_tools]
                        status_type = "busy"
                        status_detail = {"type": "busy", "reason": "tool_running", "tools": tool_names}
                    else:
                        # Check if last message is from user (agent is processing it)
                        last_msg_is_user = _check_last_message_is_user(api, session_id)
                        if last_msg_is_user:
                            status_type = "busy"
                            status_detail = {"type": "busy", "reason": "processing_user_message"}
                        else:
                            # Check if session was recently updated (within 30 seconds)
                            time_info = session.get("time", {})
                            updated = time_info.get("updated", 0)
                            now = time.time() * 1000
                            age_ms = now - updated if updated else float('inf')
                            
                            if age_ms < 30000:  # Updated within 30 seconds
                                status_type = "busy"
                                status_detail = {"type": "busy", "reason": "recently_updated"}
                            else:
                                status_type = "idle"
                                status_detail = {"type": "idle"}
        except:
            return None
    
    # Check for pending permissions (always check, regardless of source)
    permissions = api.get_permissions()
    session_perms = [p for p in permissions if p.get("sessionID") == session_id]
    
    # Check if blocked on question tool
    question_blocked = _check_question_blocked(api, session_id)
    
    # Check for running tool calls
    running_tools = _check_running_tools(api, session_id)
    
    # Override status if blocked
    if session_perms:
        status_type = "busy"
    elif question_blocked is not None:
        status_type = "busy"
    elif running_tools and status_type == "idle":
        status_type = "busy"
        status_detail = {"type": "busy", "reason": "tool_running",
                        "tools": [t.get("tool", "?") for t in running_tools]}
    
    return {
        "session_id": session_id,
        "status": status_type,
        "detail": status_detail,
        "permissions": session_perms,
        "question_blocked": question_blocked is not None,
        "question_data": question_blocked,
        "running_tools": running_tools,
    }


def _check_question_blocked(api: OpenCodeAPI, session_id: str):
    """Check if session is blocked on a question tool call."""
    try:
        messages = api.get_session_messages(session_id)
    except:
        return None
    
    if not messages:
        return None
    
    # Check the last assistant message for question tool calls
    for msg in reversed(messages):
        info = msg.get("info", {})
        if info.get("role") != "assistant":
            continue
        
        parts = msg.get("parts", [])
        for part in parts:
            if part.get("type") == "tool" and part.get("tool") == "question":
                state = part.get("state", {})
                if state.get("status") in ("pending", "running", None):
                    return part
        break
    
    return None


def _check_running_tools(api: OpenCodeAPI, session_id: str):
    """Check if session has any running tool calls in the last assistant message.
    
    Returns list of running tool parts, or empty list.
    Catches tools like bash, edit, patch, write etc. that are in progress.
    """
    try:
        messages = api.get_session_messages(session_id)
    except:
        return []
    
    if not messages:
        return []
    
    running = []
    for msg in reversed(messages):
        info = msg.get("info", {})
        if info.get("role") != "assistant":
            continue
        
        parts = msg.get("parts", [])
        for part in parts:
            if part.get("type") == "tool":
                state = part.get("state", {})
                if state.get("status") in ("pending", "running", None):
                    running.append(part)
        break  # only check the last assistant message
    
    return running


def _check_last_message_is_user(api: OpenCodeAPI, session_id: str):
    """Check if the last message in the session is from the user.
    
    If the last message is from the user, the agent is definitely processing
    (or queued to process) — even if no tools are running and time.updated
    is stale. This catches long LLM calls where nothing else changes.
    """
    try:
        messages = api.get_session_messages(session_id)
    except:
        return False
    
    if not messages:
        return False
    
    last_msg = messages[-1]
    info = last_msg.get("info", {})
    return info.get("role") == "user"


def _print_session_info(info: dict):
    """Print session info."""
    console.print(f"Session: [cyan]{info['session_id']}[/cyan]")
    console.print(f"Status:  [green]{info['status']}[/green]")
    
    # Extra info for retry status
    if info['status'] == "retry":
        detail = info['detail']
        attempt = detail.get("attempt", "?")
        message = detail.get("message", "")
        nxt = detail.get("next", "?")
        action = detail.get("action", {})
        reason = action.get("reason", "")
        provider = action.get("provider", "")
        console.print(f"Retry:   attempt {attempt}, next in {nxt}s")
        if provider:
            console.print(f"Provider: {provider}")
        if reason:
            console.print(f"Reason:  {reason}")
        if message:
            console.print(f"Message: {message}")
    
    # Permissions
    if info['permissions']:
        console.print(f"\nPermissions: [yellow]{len(info['permissions'])} pending[/yellow]")
        for p in info['permissions']:
            pid = p.get("id", "?")
            perm = p.get("permission", "?")
            patterns = p.get("patterns", [])
            console.print(f"  [green][{pid}[/green]] {perm}: {', '.join(patterns)}")
    else:
        console.print("Permissions: none")
    
    # Questions
    if info['question_blocked']:
        console.print(f"\nQuestions: [red]BLOCKED[/red] (question tool call pending)")
        question_part = info['question_data']
        if question_part:
            state = question_part.get("state", {})
            input_data = state.get("input", {})
            if input_data:
                questions = input_data.get("questions", [])
                for i, q in enumerate(questions):
                    header = q.get("header", "?")
                    question = q.get("question", "?")
                    options = q.get("options", [])
                    console.print(f"  Q{i+1}: [cyan]{header}[/cyan]")
                    console.print(f"      {question}")
                    for j, opt in enumerate(options, 1):
                        console.print(f"        {j}. {opt.get('label', '?')}: {opt.get('description', '')}")
    else:
        console.print("Questions: none")
    
    # Running tools
    running_tools = info.get('running_tools', [])
    if running_tools:
        tool_names = [t.get("tool", "?") for t in running_tools]
        console.print(f"\nTools:    [yellow]{', '.join(tool_names)}[/yellow] running")
    elif info['status'] == 'busy' and info.get('detail', {}).get('reason') == 'tool_running':
        console.print(f"\nTools:    [yellow]running[/yellow]")


def _monitor_session(api: OpenCodeAPI, session_id: str, interval: int):
    """Monitor session until blocked or idle.
    
    Only prints when status changes. For retry, waits for configurable timeout
    (default 60s) before allowing termination on next interval check.
    """
    from ..config import get_config_value
    
    retry_timeout = int(get_config_value("monitor_retry_timeout") or 60)
    
    console.print(f"Monitoring [cyan]{session_id}[/cyan] (Ctrl+C to stop)...")
    console.print()
    
    prev_status = None
    prev_permissions = False
    prev_question_blocked = False
    retry_start = None
    retry_threshold_met = False
    
    try:
        while True:
            info = _get_session_info(api, session_id)
            if info is None:
                console.print(f"[red]Session not found: {session_id}[/red]")
                raise SystemExit(1)
            
            current_status = info['status']
            current_permissions = bool(info['permissions'])
            current_question_blocked = info['question_blocked']
            
            # Detect status change
            status_changed = (
                current_status != prev_status or
                current_permissions != prev_permissions or
                current_question_blocked != prev_question_blocked
            )
            
            if status_changed:
                # Print status on change
                _print_session_info(info)
                
                # Track retry state
                if current_status == "retry":
                    if retry_start is None:
                        retry_start = time.time()
                        retry_threshold_met = False
                else:
                    # Status changed away from retry - reset
                    retry_start = None
                    retry_threshold_met = False
                
                # Check if we should stop (only on status change)
                stop, reason = _should_stop(info)
                
                if stop:
                    console.print()
                    if reason == "IDLE":
                        console.print("[green]✓ Session completed (idle)[/green]")
                    elif reason == "PERMISSION":
                        console.print("[yellow]⚠ Session blocked on permission request[/yellow]")
                        console.print("  Run: [cyan]opencode-tool permission grant <session_id> once|always|reject[/cyan]")
                    elif reason == "QUESTION":
                        console.print("[yellow]⚠ Session blocked on question[/yellow]")
                        console.print("  Run: [cyan]opencode-tool question get <session_id>[/cyan]")
                        console.print("  Then: [cyan]opencode-tool question reply <request_id> \"Answer\"[/cyan]")
                    elif reason == "RETRY":
                        detail = info['detail']
                        message = detail.get("message", "")
                        console.print("[yellow]⚠ Session retrying...[/yellow]")
                        if message:
                            console.print(f"  Message: {message}")
                    raise SystemExit(0)
            
            # Check retry timeout (only if retry threshold met AND still retrying)
            if retry_start and current_status == "retry":
                elapsed = time.time() - retry_start
                
                if elapsed >= retry_timeout:
                    retry_threshold_met = True
                
                # Only terminate if threshold was met on a PREVIOUS check
                # (gives one more interval for status to change)
                if retry_threshold_met and status_changed is False:
                    # Threshold was met before this check, and status didn't change
                    # This means we've been retrying for >= timeout with no change
                    console.print(f"\n[yellow]⚠ Retry timeout after {int(elapsed)}s (threshold: {retry_timeout}s)[/yellow]")
                    raise SystemExit(1)
            
            # Update previous state
            prev_status = current_status
            prev_permissions = current_permissions
            prev_question_blocked = current_question_blocked
            
            time.sleep(interval)
    
    except KeyboardInterrupt:
        console.print("\nStopped monitoring.")
        raise SystemExit(0)


def _should_stop(info: dict) -> tuple:
    """Check if monitoring should stop."""
    status = info['status']
    
    if info['permissions']:
        return True, "PERMISSION"
    
    if info['question_blocked']:
        return True, "QUESTION"
    
    if status == "idle":
        return True, "IDLE"
    
    if status == "retry":
        return True, "RETRY"
    
    return False, None


@session.command()
@click.argument("session_id")
def interrupt(session_id: str):
    """Abort a running session."""
    api = OpenCodeAPI()
    
    if api.abort_session(session_id):
        console.print(f"[green]aborted: {session_id}[/green]")
    else:
        console.print(f"[red]failed to abort: {session_id}[/red]")
        raise SystemExit(1)


@session.command("messages")
@click.argument("session_id")
@click.option("--limit", "-n", default=20, help="Number of messages to show")
@click.option("--offset", default=0, help="Offset for pagination")
@click.option("--last", "-l", type=int, help="Get last N messages")
@click.option("--role", type=click.Choice(["user", "assistant"]), help="Filter by role")
@click.option("--hide-tools", is_flag=True, help="Hide tool call results")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def messages(session_id: str, limit: int, offset: int, last: Optional[int], role: Optional[str], hide_tools: bool, json_out: bool):
    """Get messages from a session with filtering and pagination."""
    api = OpenCodeAPI()
    
    try:
        all_messages = api.get_session_messages(session_id)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    
    if not all_messages:
        console.print("[yellow]No messages found[/yellow]")
        return
    
    # Filter by role
    if role:
        all_messages = [m for m in all_messages if m.get("info", {}).get("role") == role]
    
    # Filter out tool results if requested
    if hide_tools:
        filtered = []
        for msg in all_messages:
            info = msg.get("info", {})
            parts = msg.get("parts", [])
            # Keep user messages and assistant messages without tool results
            if info.get("role") == "user":
                filtered.append(msg)
            elif info.get("role") == "assistant":
                # Check if it has only text parts (no tool calls/results)
                has_tool = any(p.get("type") in ("tool", "tool-call", "tool-result") for p in parts)
                if not has_tool:
                    filtered.append(msg)
        all_messages = filtered
    
    total = len(all_messages)
    
    # Apply --last (get last N messages)
    if last is not None:
        all_messages = all_messages[-last:]
        offset = 0  # Reset offset when using --last
    
    # Apply pagination
    all_messages = all_messages[offset:offset + limit]
    
    if json_out:
        print(json.dumps({
            "session_id": session_id,
            "messages": all_messages,
            "total": total,
            "offset": offset,
            "limit": limit
        }, indent=2))
        return
    
    if not all_messages:
        console.print("[yellow]No messages found[/yellow]")
        return
    
    console.print(f"Messages for [cyan]{session_id}[/cyan] (showing {offset + 1}-{min(offset + limit, total)} of {total}):\n")
    
    for msg in all_messages:
        info = msg.get("info", {})
        parts = msg.get("parts", [])
        role = info.get("role", "?")
        
        # Role color
        if role == "user":
            role_color = "blue"
        elif role == "assistant":
            role_color = "green"
        else:
            role_color = "yellow"
        
        console.print(f"[{role_color}]{(role or '?').upper()}[/{role_color}]")
        
        for part in parts:
            ptype = part.get("type", "?")
            
            if ptype == "text":
                text = part.get("text", "")
                # Truncate long text
                if len(text) > 500:
                    text = text[:500] + "..."
                console.print(f"  {text}")
            elif ptype == "tool":
                tool_name = part.get("tool", "?")
                state = part.get("state", {})
                status = state.get("status", "?")
                if not hide_tools:
                    console.print(f"  [dim]tool: {tool_name} ({status})[/dim]")
            elif ptype == "tool-call":
                tool_name = part.get("name", "?")
                if not hide_tools:
                    console.print(f"  [dim]tool-call: {tool_name}[/dim]")
            elif ptype == "tool-result":
                if not hide_tools:
                    result = part.get("result", "")
                    if isinstance(result, str) and len(result) > 200:
                        result = result[:200] + "..."
                    console.print(f"  [dim]tool-result: {result}[/dim]")
        
        console.print()
