"""Run command for OpenCode - API-based implementation."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from ..api import OpenCodeAPI
from ..config import get_config_value

console = Console()
DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


@click.command()
@click.argument("prompt", required=True)
@click.option("-c", "--continue", "continue_last", is_flag=True, help="Continue the last session")
@click.option("-s", "--session", "session_id", help="Continue a specific session")
@click.option("-t", "--title", help="Session title (new sessions only)")
@click.option("-d", "--dir", "working_dir", default=None, help="Working directory")
@click.option("-w", "--wait", is_flag=True, help="Wait for completion")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
@click.option("-m", "--model", help="Model to use: provider,model_name or just model_name (default: from config)")
@click.option("-v", "--variant", help="Reasoning effort variant (default: from config)")
@click.option("--steer", is_flag=True, help="Interrupt session first, then send (requires -s)")
def run(
    prompt: str,
    continue_last: bool,
    session_id: Optional[str],
    title: Optional[str],
    working_dir: Optional[str],
    wait: bool,
    json_out: bool,
    model: Optional[str],
    variant: Optional[str],
    steer: bool,
):
    """Run a prompt on OpenCode server."""
    # Parse model: comma-delimited "provider,model_name" or just "model_name"
    provider_id = None
    model_id = model
    if model and "," in model:
        parts = model.split(",", 1)
        provider_id = parts[0].strip()
        model_id = parts[1].strip()

    api = OpenCodeAPI()
    
    # Get config defaults
    config_model = get_config_value("default_model")
    config_variant = get_config_value("default_variant")
    
    # For existing sessions, get session's current model as fallback
    session_model = None
    session_variant = None
    if session_id:
        try:
            session = api.get_session(session_id)
            model_info = session.get("model", {})
            if isinstance(model_info, dict):
                session_model = model_info.get("id")
                session_variant = model_info.get("variant")
        except:
            pass
    
    # Apply fallback: explicit flag > session model > config default
    if not model:
        model = session_model or config_model
    if not variant:
        variant = session_variant or config_variant
    
    # Check server
    if not api.is_healthy():
        if json_out:
            print(json.dumps({"error": "OpenCode server not running", "success": False}))
        else:
            console.print("[red]error: server not running[/red]")
        raise SystemExit(1)
    
    # --steer requires -s
    if steer and not session_id:
        console.print("[red]error: --steer requires -s <session_id>[/red]")
        raise SystemExit(1)
    
    # Resolve --continue to session ID
    if continue_last and not session_id:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.execute("SELECT id FROM session ORDER BY time_updated DESC LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row:
                session_id = row[0]
        except:
            pass
    
    # Handle --steer: interrupt first, then send
    if steer and session_id:
        console.print(f"Steering: interrupting {session_id}...", style="yellow")
        if api.abort_session(session_id):
            console.print("Interrupted. Sending new message...", style="yellow")
            time.sleep(1)
        else:
            console.print("Warning: interrupt may have failed, sending anyway...", style="yellow")
    
    try:
        # Create session if needed
        if not session_id:
            session = api.create_session(
                model=model_id,
                provider=provider_id,
                variant=variant,
                directory=working_dir
            )
            session_id = session["id"]
        
        # Send message async
        api.send_message_async(
            session_id=session_id,
            prompt=prompt,
            model=model_id,
            provider=provider_id,
            variant=variant
        )
        
        # Output result
        if json_out:
            print(json.dumps({
                "session_id": session_id,
                "status": "queued",
                "model": model,
                "variant": variant
            }))
        else:
            console.print(session_id)
        
        # Wait for completion if requested
        if wait:
            _wait_for_completion(api, session_id)
    
    except Exception as e:
        if json_out:
            print(json.dumps({"error": str(e), "success": False}))
        else:
            console.print(f"[red]error: {e}[/red]")
        raise SystemExit(1)


def _wait_for_completion(api: OpenCodeAPI, session_id: str, timeout: int = 600):
    """Wait for a session to complete."""
    console.print(f"Waiting for {session_id} to complete...", style="yellow")
    
    start = time.time()
    while time.time() - start < timeout:
        info = api.get_session_status()
        status = info.get(session_id, {})
        
        if status.get("type") == "idle":
            console.print("[green]✓ Session completed[/green]")
            return
        
        # Check for blocking
        permissions = api.get_permissions()
        session_perms = [p for p in permissions if p.get("sessionID") == session_id]
        if session_perms:
            console.print("[yellow]⚠ Session blocked on permission[/yellow]")
            console.print(f"  Run: opencode-tool permission grant {session_id} once")
            return
        
        time.sleep(2)
    
    console.print(f"[yellow]⚠ Timeout after {timeout}s[/yellow]")
