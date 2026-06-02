"""Send command for OpenCode."""

import json
import subprocess
import sys
import time
import sqlite3
from pathlib import Path
from typing import Optional

import click
import requests
from rich.console import Console

from ..api import OpenCodeAPI
from ..config import get_server_url

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
@click.option("-m", "--model", help="Model to use")
@click.option("-v", "--variant", help="Reasoning effort variant")
@click.option("--steer", is_flag=True, help="Interrupt session first, then send (requires -s)")
def send(
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
    """Send a prompt to OpenCode server."""
    import os
    
    if working_dir is None:
        working_dir = os.environ.get("PWD", os.getcwd())
    
    # Check server
    api = OpenCodeAPI()
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
    
    # Build command
    server_url = get_server_url()
    cmd = [
        "opencode", "run", "--attach", server_url,
        "--dangerously-skip-permissions",
        "--dir", working_dir,
        "--format", "json",
    ]
    if session_id:
        cmd.extend(["-s", session_id])
    if title:
        cmd.extend(["--title", title])
    if model:
        cmd.extend(["--model", model])
    if variant:
        cmd.extend(["--variant", variant])
    cmd.append(prompt)
    
    # For wait mode: run synchronously
    if wait:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout.strip()
        if json_out:
            print(output)
        else:
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        evt = json.loads(line)
                        ptype = evt.get("part", {}).get("type", "")
                        text = evt.get("part", {}).get("text", "")
                        if ptype == "text" and text:
                            console.print(text)
                    except json.JSONDecodeError:
                        console.print(line)
                else:
                    console.print(line)
        return
    
    # Fire-and-forget: run in background, wait for step_start event
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    
    found_session_id = None
    deadline = time.time() + 40
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            continue
        line = line.strip()
        if line.startswith("{"):
            try:
                evt = json.loads(line)
                if "sessionID" in evt:
                    found_session_id = evt["sessionID"]
                if found_session_id and evt.get("type") in ("step_start", "text"):
                    break
            except json.JSONDecodeError:
                pass
    
    # Detach
    try:
        proc.kill()
    except:
        pass
    try:
        proc.wait(timeout=2)
    except:
        pass
    
    # Fallback
    if not found_session_id:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.execute("SELECT id FROM session ORDER BY time_created DESC LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row:
                found_session_id = row[0]
        except:
            pass
    
    if json_out:
        print(json.dumps({"session_id": found_session_id, "status": "queued"}))
    else:
        console.print(found_session_id if found_session_id else "sent (unknown session)")
