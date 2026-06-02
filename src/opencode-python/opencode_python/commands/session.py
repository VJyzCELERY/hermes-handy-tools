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


@session.command()
@click.argument("session_id")
@click.option("--monitor", is_flag=True, help="Monitor until blocked/idle")
@click.option("--interval", default=10, help="Monitor interval in seconds")
def status(session_id: str, monitor: bool, interval: int):
    """Check session status."""
    api = OpenCodeAPI()
    
    if monitor:
        _monitor_session(api, session_id, interval)
    else:
        _check_session(api, session_id)


def _check_session(api: OpenCodeAPI, session_id: str):
    """Check session status once."""
    info = _get_session_info(api, session_id)
    if info is None:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise SystemExit(1)
    
    _print_session_info(info)


def _get_session_info(api: OpenCodeAPI, session_id: str) -> Optional[dict]:
    """Get full session info."""
    # Check session status
    statuses = api.get_session_status()
    status = statuses.get(session_id)
    
    if status is None:
        # Check if session exists
        try:
            session = api.get_session(session_id)
            if not session:
                return None
            status_type = "idle"
            status_detail = {}
        except:
            return None
    else:
        status_type = status.get("type", "unknown")
        status_detail = status
    
    # Check for pending permissions
    permissions = api.get_permissions()
    session_perms = [p for p in permissions if p.get("sessionID") == session_id]
    
    # Check if blocked on question tool
    question_blocked = _check_question_blocked(api, session_id)
    
    return {
        "session_id": session_id,
        "status": status_type,
        "detail": status_detail,
        "permissions": session_perms,
        "question_blocked": question_blocked is not None,
        "question_data": question_blocked,
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


def _monitor_session(api: OpenCodeAPI, session_id: str, interval: int):
    """Monitor session until blocked or idle."""
    console.print(f"Monitoring [cyan]{session_id}[/cyan] (Ctrl+C to stop)...")
    console.print()
    
    try:
        while True:
            info = _get_session_info(api, session_id)
            if info is None:
                console.print(f"[red]Session not found: {session_id}[/red]")
                raise SystemExit(1)
            
            _print_session_info(info)
            stop, reason = _should_stop(info)
            
            if stop:
                console.print()
                if reason == "IDLE":
                    console.print("[green]✓ Session completed (idle)[/green]")
                elif reason == "PERMISSION":
                    console.print("[yellow]⚠ Session blocked on permission request[/yellow]")
                    console.print("  Run: [cyan]opencode-python permission grant <session_id> once|always|reject[/cyan]")
                elif reason == "QUESTION":
                    console.print("[yellow]⚠ Session blocked on question[/yellow]")
                    console.print("  Run: [cyan]opencode-python question get <session_id>[/cyan]")
                    console.print("  Then: [cyan]opencode-python question reply <request_id> \"Answer\"[/cyan]")
                elif reason == "RETRY":
                    detail = info['detail']
                    nxt = detail.get("next", "?")
                    message = detail.get("message", "")
                    console.print(f"[yellow]⚠ Session retrying (next attempt in {nxt}s)[/yellow]")
                    if message:
                        console.print(f"  Message: {message}")
                raise SystemExit(0)
            
            console.print(f"\n--- checking again in {interval}s ---\n")
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
