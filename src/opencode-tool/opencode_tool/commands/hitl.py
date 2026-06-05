"""HITL (Human-In-The-Loop) management commands for opencode-tool.

Detects and responds to permission requests and questions from the agent.
Supports REST API + message scanning + TUI control + tmux fallback.

Detection layers:
  1. REST API (fast, non-blocking)
  2. Message scanning (moderate, non-blocking)
  3. All-sessions scan (catches subagent HITL)
  4. TUI control/next (slow, blocking, with --wait)

Response layers:
  1. REST API reply (fast)
  2. TUI execute-command (fallback)
  3. Tmux keystrokes (last resort)

Usage:
    opencode-tool hitl detect <session_id> [--json] [--wait] [--timeout 5]
    opencode-tool hitl respond <session_id> <answer> [--json]
    opencode-tool hitl dismiss <session_id> [--json]
"""

import json
import os
from typing import Optional, Tuple

import click
from rich.console import Console

from ..api import OpenCodeAPI
console = Console()


def _get_hitl_type(result: Optional[dict]) -> str:
    """Determine HITL type from detection result."""
    if result is None:
        return "none"
    if result.get("permissions") or result.get("detail", {}).get("reason") == "permission_pending":
        return "permission"
    if result.get("question_blocked") or result.get("question_data"):
        return "question"
    # TUI control request
    if result.get("path"):
        return "control-request"
    return "unknown"


# ── Detection layers ──

def _detect_rest(api: OpenCodeAPI, session_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Layer 1: REST API detection (fast, non-blocking)."""
    try:
        from ..commands.session import _get_session_info
        info = _get_session_info(api, session_id)
        if info and (info.get("permissions") or info.get("question_blocked")):
            # Check if this is a subagent and include parent ID
            try:
                session_info = api.get_session(session_id)
                parent_id = session_info.get("parentID")
                if parent_id:
                    info["parent_session_id"] = parent_id
                    info["blocked_session_id"] = session_id
                    info["blocked_session_title"] = f"subagent of {parent_id}"
            except Exception:
                pass
            return info, "rest-api"
    except Exception:
        pass
    return None, None


def _detect_messages(api: OpenCodeAPI, session_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Layer 2: Message scanning (moderate, non-blocking)."""
    try:
        from ..commands.question import _scan_session_questions
        questions = _scan_session_questions(api, session_id)
        if questions:
            return {"question_blocked": True, "question_data": questions}, "message-scan"
    except Exception:
        pass
    return None, None


def _detect_all_sessions(api: OpenCodeAPI, exclude_session: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Layer 3: Check ALL active sessions for any blocked state.

    Catches HITL from subagents — when a subagent spawns and gets blocked,
    the parent session may not show it, but the subagent's session will.

    Also scans parent sessions for running `task` tools and checks their
    subagent sessions directly (subagent sessions aren't in get_sessions()).

    Returns the first blocked session found (with session_id in the result).
    """
    try:
        sessions = api.get_sessions()
        for s in sessions:
            sid = s.get("id")
            if not sid or sid == exclude_session:
                continue

            try:
                from ..commands.session import _get_session_info
                info = _get_session_info(api, sid)
                if info and (info.get("permissions") or info.get("question_blocked")):
                    # Include the session_id so caller knows which session is blocked
                    result = dict(info)
                    result["blocked_session_id"] = sid
                    result["blocked_session_title"] = s.get("title", "untitled")
                    return result, "all-sessions-scan"
            except Exception:
                continue

        # Also check for subagent sessions (not in get_sessions list)
        # Scan parent sessions for running task tools with subagent session IDs
        subagent_result, subagent_source = _detect_subagent_hitl(api, exclude_session)
        if subagent_result:
            return subagent_result, subagent_source

        # Also try querying the excluded session directly for subagent HITL
        # (it might not be in get_sessions() due to project filtering)
        if exclude_session:
            subagent_result, subagent_source = _detect_subagent_hitl_from_session(api, exclude_session)
            if subagent_result:
                return subagent_result, subagent_source

    except Exception:
        pass
    return None, None


def _detect_subagent_hitl_from_session(api: OpenCodeAPI, session_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Detect HITL in subagent sessions of a specific parent session.

    This handles the case where the parent session isn't in get_sessions()
    due to project/directory filtering, but we know its ID.
    """
    try:
        messages = api.get_session_messages(session_id)
    except Exception:
        return None, None

    if not messages:
        return None, None

    # Scan messages for task tools with subagent session IDs
    subagent_ids = set()
    for msg in messages:
        info = msg.get("info", {})
        if info.get("role") != "assistant":
            continue
        parts = msg.get("parts", [])
        for part in parts:
            if part.get("type") != "tool" or part.get("tool") != "task":
                continue
            state = part.get("state", {})
            metadata = state.get("metadata", {})
            subagent_sid = metadata.get("sessionId")
            if subagent_sid:
                subagent_ids.add(subagent_sid)

    # Check each subagent session for HITL
    for subagent_sid in subagent_ids:
        try:
            sub_messages = api.get_session_messages(subagent_sid)
            if not sub_messages:
                continue

            # Check for pending questions
            for msg in reversed(sub_messages):
                msg_info = msg.get("info", {})
                if msg_info.get("role") != "assistant":
                    continue
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") == "tool" and part.get("tool") == "question":
                        state = part.get("state", {})
                        # For question tools: "pending" or "running" = waiting for user input
                        if state.get("status") in ("pending", "running", None):
                            result = {
                                "session_id": subagent_sid,
                                "status": "busy",
                                "detail": {"type": "busy", "reason": "subagent_question_blocked"},
                                "permissions": [],
                                "question_blocked": True,
                                "question_data": part,
                                "running_tools": [],
                                "blocked_session_id": subagent_sid,
                                "blocked_session_title": f"subagent of {session_id}",
                                "parent_session_id": session_id,
                            }
                            return result, "subagent-scan"
                break

            # Check for pending permissions
            try:
                permissions = api.get_permissions()
                subagent_perms = [p for p in permissions if p.get("sessionID") == subagent_sid]
                if subagent_perms:
                    result = {
                        "session_id": subagent_sid,
                        "status": "busy",
                        "detail": {"type": "busy", "reason": "subagent_permission_blocked"},
                        "permissions": subagent_perms,
                        "question_blocked": False,
                        "question_data": None,
                        "running_tools": [],
                        "blocked_session_id": subagent_sid,
                        "blocked_session_title": f"subagent of {session_id}",
                        "parent_session_id": session_id,
                    }
                    return result, "subagent-scan"
            except Exception:
                pass

        except Exception:
            continue

    return None, None


def _detect_if_subagent(api: OpenCodeAPI, session_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Check if a session is a subagent and detect its HITL.

    Uses the session's parentID field to find the parent session.
    If the session has HITL, returns it with the parent session ID.
    """
    # Get session info to check for parentID
    try:
        session_info = api.get_session(session_id)
        parent_id = session_info.get("parentID")
    except Exception:
        parent_id = None

    # Check if this session has HITL directly
    try:
        messages = api.get_session_messages(session_id)
        if messages:
            for msg in reversed(messages):
                msg_info = msg.get("info", {})
                if msg_info.get("role") != "assistant":
                    continue
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") == "tool" and part.get("tool") == "question":
                        state = part.get("state", {})
                        if state.get("status") in ("pending", "running", None):
                            # Found blocked subagent
                            result = {
                                "session_id": session_id,
                                "status": "busy",
                                "detail": {"type": "busy", "reason": "subagent_question_blocked"},
                                "permissions": [],
                                "question_blocked": True,
                                "question_data": part,
                                "running_tools": [],
                                "blocked_session_id": session_id,
                                "blocked_session_title": f"subagent of {parent_id}" if parent_id else "subagent",
                                "parent_session_id": parent_id,
                            }
                            return result, "subagent-scan"
                break
    except Exception:
        pass

    return None, None


def _detect_subagent_hitl(api: OpenCodeAPI, exclude_session: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Detect HITL in subagent sessions.

    Subagent sessions aren't in get_sessions() list, but their IDs are
    embedded in parent session's `task` tool metadata. This function:
    1. Scans ALL sessions for task tools with subagent session IDs
    2. Queries each subagent session directly for HITL

    Note: We do NOT exclude the parent session here — we need to scan it
    to find subagent IDs. The exclude_session is only used to skip checking
    subagent sessions as parents (they won't have task tools anyway).
    """
    try:
        sessions = api.get_sessions()
        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue

            try:
                messages = api.get_session_messages(sid)
            except Exception:
                continue

            # Scan messages for task tools with subagent session IDs
            subagent_ids = set()
            for msg in messages:
                info = msg.get("info", {})
                if info.get("role") != "assistant":
                    continue
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") != "tool" or part.get("tool") != "task":
                        continue
                    state = part.get("state", {})
                    metadata = state.get("metadata", {})
                    subagent_sid = metadata.get("sessionId")
                    if subagent_sid:
                        subagent_ids.add(subagent_sid)

            # Check each subagent session for HITL
            for subagent_sid in subagent_ids:
                try:
                    # Query subagent session messages directly
                    sub_messages = api.get_session_messages(subagent_sid)
                    if not sub_messages:
                        continue

                    # Check for pending questions
                    for msg in reversed(sub_messages):
                        msg_info = msg.get("info", {})
                        if msg_info.get("role") != "assistant":
                            continue
                        parts = msg.get("parts", [])
                        for part in parts:
                            if part.get("type") == "tool" and part.get("tool") == "question":
                                state = part.get("state", {})
                                # For question tools: "pending" or "running" = waiting for user input
                                if state.get("status") in ("pending", "running", None):
                                    # Found blocked subagent!
                                    result = {
                                        "session_id": subagent_sid,
                                        "status": "busy",
                                        "detail": {"type": "busy", "reason": "subagent_question_blocked"},
                                        "permissions": [],
                                        "question_blocked": True,
                                        "question_data": part,
                                        "running_tools": [],
                                        "blocked_session_id": subagent_sid,
                                        "blocked_session_title": f"subagent of {sid}",
                                        "parent_session_id": sid,
                                    }
                                    return result, "subagent-scan"
                        break

                    # Check for pending permissions
                    try:
                        permissions = api.get_permissions()
                        subagent_perms = [p for p in permissions if p.get("sessionID") == subagent_sid]
                        if subagent_perms:
                            result = {
                                "session_id": subagent_sid,
                                "status": "busy",
                                "detail": {"type": "busy", "reason": "subagent_permission_blocked"},
                                "permissions": subagent_perms,
                                "question_blocked": False,
                                "question_data": None,
                                "running_tools": [],
                                "blocked_session_id": subagent_sid,
                                "blocked_session_title": f"subagent of {sid}",
                                "parent_session_id": sid,
                            }
                            return result, "subagent-scan"
                    except Exception:
                        pass

                except Exception:
                    continue

    except Exception:
        pass
    return None, None


def _detect_tui(api: OpenCodeAPI, timeout: int = 5) -> Tuple[Optional[dict], Optional[str]]:
    """Layer 4: TUI control/next (slow, blocking)."""
    request = api.tui_control_next(timeout=timeout)
    if request:
        return request, "tui-control"
    return None, None


def _detect_all(
    api: OpenCodeAPI,
    session_id: str,
    wait: bool = False,
    timeout: int = 5,
    check_all_sessions: bool = True,
) -> Tuple[Optional[dict], Optional[str]]:
    """Run all detection layers in order."""
    # Layer 1: REST API (target session)
    result, source = _detect_rest(api, session_id)
    if result:
        return result, source

    # Layer 2: Message scan (target session)
    result, source = _detect_messages(api, session_id)
    if result:
        return result, source

    # Layer 3: All-sessions scan (catches subagent HITL)
    if check_all_sessions:
        result, source = _detect_all_sessions(api, exclude_session=session_id)
        if result:
            return result, source

        # Also check if the target session itself is a subagent
        result, source = _detect_if_subagent(api, session_id)
        if result:
            return result, source

    # Layer 4: TUI (with --wait)
    if wait:
        result, source = _detect_tui(api, timeout)
        if result:
            return result, source

    return None, None


# ── Response layers ──

def _respond_permission_rest(api: OpenCodeAPI, session_id: str, answer: str) -> bool:
    """Respond to permission via REST API."""
    permissions = api.get_permissions()
    session_perms = [p for p in permissions if p.get("sessionID") == session_id]

    if not session_perms:
        return False

    for p in session_perms:
        pid = p.get("id")
        if pid:
            api.reply_permission(pid, answer)
    return True


def _respond_question_rest(api: OpenCodeAPI, session_id: str, answer: str) -> bool:
    """Respond to question via REST API."""
    from ..commands.question import _scan_session_questions

    questions = _scan_session_questions(api, session_id)
    if not questions:
        return False

    q = questions[0]
    qid = q.get("id")

    try:
        all_questions = api.get_questions()
        match = next(
            (aq for aq in all_questions if aq.get("tool", {}).get("callID") == qid),
            None,
        )
        if match:
            request_id = match.get("id")
            answers_array = [[answer]]
            api.reply_question(request_id, answers_array)
            return True
    except Exception:
        pass

    return False


def _respond_via_tmux(answer: str, hitl_type: str) -> bool:
    """Respond to HITL via tmux keystrokes (last resort).

    Finds the tmux session for the current profile and sends keystrokes.
    """
    try:
        from ..tmux import (
            find_profile_tmux_session,
            tmux_respond_question,
            tmux_respond_permission,
            is_tmux_available,
        )

        if not is_tmux_available():
            return False

        tmux_session = find_profile_tmux_session()
        if not tmux_session:
            return False

        if hitl_type == "question":
            return tmux_respond_question(tmux_session, answer)
        elif hitl_type == "permission":
            return tmux_respond_permission(tmux_session, answer)
        return False
    except Exception:
        return False


def _find_parent_session(api: OpenCodeAPI, subagent_session_id: str) -> Optional[str]:
    """Find the parent session ID for a subagent.

    Scans all sessions for task tools that reference this subagent.
    Returns the parent session ID or None.
    """
    try:
        sessions = api.get_sessions()
        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue
            try:
                messages = api.get_session_messages(sid)
            except Exception:
                continue
            for msg in messages:
                info = msg.get("info", {})
                if info.get("role") != "assistant":
                    continue
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") != "tool" or part.get("tool") != "task":
                        continue
                    state = part.get("state", {})
                    metadata = state.get("metadata", {})
                    if metadata.get("sessionId") == subagent_session_id:
                        return sid
    except Exception:
        pass
    return None


def _respond_via_parent(api: OpenCodeAPI, parent_session_id: str, answer: str, directory: Optional[str] = None) -> bool:
    """Respond to a subagent's HITL by sending the answer through the parent session.

    The parent session can provide the answer that the subagent needs.
    """
    try:
        # Send the answer as a message to the parent session
        prompt = f"The answer to the subagent's question is: {answer}"
        api.send_message_async(parent_session_id, prompt, directory=directory)
        return True
    except Exception:
        return False


def _print_hitl_details(result: dict):
    """Print HITL detection details."""
    hitl_type = _get_hitl_type(result)

    if hitl_type == "permission":
        permissions = result.get("permissions", [])
        for p in permissions:
            perm = p.get("permission", "?")
            patterns = p.get("patterns", [])
            console.print(f"  Permission: [cyan]{perm}[/cyan]")
            console.print(f"  Patterns:   {', '.join(patterns)}")

    elif hitl_type == "question":
        question_data = result.get("question_data")
        if question_data and isinstance(question_data, dict):
            input_data = question_data.get("state", {}).get("input", {})
            questions = input_data.get("questions", [])
        elif question_data and isinstance(question_data, list):
            # From message scan — question_data is the list of questions
            questions = question_data[0].get("questions", []) if question_data else []
        else:
            questions = []

        for i, q in enumerate(questions):
            header = q.get("header", "?")
            question = q.get("question", "?")
            options = q.get("options", [])
            console.print(f"  Q{i + 1}: [cyan]{header}[/cyan]")
            console.print(f"      {question}")
            for j, opt in enumerate(options, 1):
                label = opt.get("label", "?")
                desc = opt.get("description", "")
                console.print(f"        {j}. {label}: {desc}")

    elif hitl_type == "control-request":
        path = result.get("path", "?")
        body = result.get("body", {})
        console.print(f"  Path: [cyan]{path}[/cyan]")
        console.print(f"  Body: {json.dumps(body, indent=2)}")


# ── Commands ──

@click.group()
def hitl():
    """Manage Human-In-The-Loop requests.

    Detects pending permission requests and questions from the agent.
    Supports REST API + message scanning + all-sessions scan + tmux fallback.
    """
    pass


@hitl.command("detect")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
@click.option("--wait", is_flag=True, help="Block until HITL found (uses TUI)")
@click.option("--timeout", default=5, help="Wait timeout in seconds")
@click.option("--all-sessions", "check_all", is_flag=True, help="Check all sessions (catches subagent HITL)")
def detect(session_id: str, json_out: bool, wait: bool, timeout: int, check_all: bool):
    """Detect pending HITL requests for a session.

    Tries detection layers in order:
      1. REST API (fast)
      2. Message scanning (moderate)
      3. All-sessions scan (catches subagent HITL)
      4. TUI control/next (with --wait)

    Use --all-sessions to also check other sessions for blocked state.
    This catches HITL from subagents that aren't visible in the target session.
    """
    api = OpenCodeAPI()
    profile = os.environ.get("OPENCODE_TOOL_PROFILE", "default")

    result, source = _detect_all(api, session_id, wait, timeout, check_all_sessions=check_all or True)
    hitl_type = _get_hitl_type(result)

    if json_out:
        output = {
            "session_id": session_id,
            "profile": profile,
            "type": hitl_type,
            "source": source,
            "data": result,
        }
        # If blocked session is different, include it
        if result and result.get("blocked_session_id"):
            output["blocked_session_id"] = result["blocked_session_id"]
            output["blocked_session_title"] = result.get("blocked_session_title", "")
        print(json.dumps(output, indent=2))
        return

    if not result:
        console.print("[green]No pending HITL requests[/green]")
        return

    # Show which session is blocked (if different from requested)
    blocked_sid = result.get("blocked_session_id")
    if blocked_sid and blocked_sid != session_id:
        console.print(f"[yellow]HITL detected in DIFFERENT session![/yellow]")
        console.print(f"  Requested: [cyan]{session_id}[/cyan]")
        console.print(f"  Blocked:   [cyan]{blocked_sid}[/cyan]")
        console.print(f"  Title:     {result.get('blocked_session_title', '?')}")
    else:
        console.print(f"Session: [cyan]{session_id}[/cyan]")

    console.print(f"Profile: [yellow]{profile}[/yellow]")
    console.print(f"Source:  [dim]{source}[/dim]")
    console.print(f"Type:    [bold]{hitl_type}[/bold]")
    console.print()
    _print_hitl_details(result)


@hitl.command("respond")
@click.argument("session_id")
@click.argument("answer")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def respond(session_id: str, answer: str, json_out: bool):
    """Respond to a pending HITL request.

    Auto-detects type:
      - permission: answer is 'once', 'always', or 'reject'
      - question: answer is the label or text to reply

    Tries response layers in order:
      1. REST API reply (fast)
      2. TUI execute-command (fallback)
      3. Tmux keystrokes (last resort)
    """
    api = OpenCodeAPI()

    # Detect what's pending
    result, _ = _detect_all(api, session_id)
    hitl_type = _get_hitl_type(result)

    # If blocked session is different, use that session_id
    actual_session_id = result.get("blocked_session_id", session_id) if result else session_id

    if hitl_type == "permission":
        responded = _respond_permission_rest(api, actual_session_id, answer)
        source = "rest-api" if responded else None

        if not responded:
            # TUI fallback: interrupt to clear the block
            api.tui_execute_command("session.interrupt")
            source = "tui"

        if not responded and source != "tui":
            # Tmux fallback (last resort)
            if _respond_via_tmux(answer, "permission"):
                responded = True
                source = "tmux"

        if json_out:
            print(json.dumps({
                "session_id": actual_session_id,
                "type": "permission",
                "responded": responded,
                "answer": answer,
                "source": source,
            }))
        elif responded:
            if source == "tmux":
                console.print(f"[green]Granted via tmux: {answer}[/green]")
            else:
                console.print(f"[green]Granted: {answer}[/green]")
        else:
            console.print("[red]Failed to respond to permission[/red]")

    elif hitl_type == "question":
        # Check if this is a subagent session (has parent_session_id)
        parent_session_id = result.get("parent_session_id") if result else None
        is_subagent = parent_session_id is not None

        responded = _respond_question_rest(api, actual_session_id, answer)
        source = "rest-api" if responded else None

        if not responded and is_subagent and parent_session_id:
            # Subagent question — route through parent session
            directory = None
            try:
                session_info = api.get_session(parent_session_id)
                directory = session_info.get("directory")
            except Exception:
                pass
            responded = _respond_via_parent(api, parent_session_id, answer, directory)
            source = "parent-session" if responded else None

        if not responded:
            # TUI fallback: interrupt to clear the block
            api.tui_execute_command("session.interrupt")
            source = "tui"
            responded = True  # Handled via TUI

        if not responded:
            # Tmux fallback (last resort)
            if _respond_via_tmux(answer, "question"):
                responded = True
                source = "tmux"

        if json_out:
            print(json.dumps({
                "session_id": actual_session_id,
                "parent_session_id": parent_session_id,
                "type": "question",
                "responded": responded,
                "answer": answer,
                "source": source,
            }))
        elif responded:
            if source == "parent-session":
                console.print(f"[green]Replied via parent session: {answer}[/green]")
                console.print(f"  Parent: [cyan]{parent_session_id}[/cyan]")
            elif source == "tui":
                console.print(f"[yellow]Question not replyable via API — interrupted via TUI[/yellow]")
            elif source == "tmux":
                console.print(f"[green]Replied via tmux: {answer}[/green]")
            else:
                console.print(f"[green]Replied: {answer}[/green]")
        else:
            console.print("[red]No pending question found[/red]")

    else:
        if json_out:
            print(json.dumps({
                "session_id": session_id,
                "type": "none",
                "responded": False,
                "source": None,
            }))
        else:
            console.print("[yellow]No pending HITL request found[/yellow]")


@hitl.command("dismiss")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def dismiss(session_id: str, json_out: bool):
    """Dismiss all pending HITL requests (stops agent).

    Tries in order:
      1. REST API abort
      2. TUI session.interrupt (fallback)
      3. Tmux Escape (last resort)
    """
    api = OpenCodeAPI()

    # Layer 1: REST API abort
    dismissed = api.abort_session(session_id)
    source = "rest-api" if dismissed else None

    # Layer 2: TUI fallback
    if not dismissed:
        api.tui_execute_command("session.interrupt")
        source = "tui"
        dismissed = True

    # Layer 3: Tmux fallback
    if source == "tui":
        try:
            from ..tmux import find_profile_tmux_session, tmux_dismiss_hitl, is_tmux_available
            if is_tmux_available():
                tmux_session = find_profile_tmux_session()
                if tmux_session:
                    tmux_dismiss_hitl(tmux_session)
        except Exception:
            pass

    if json_out:
        print(json.dumps({
            "session_id": session_id,
            "dismissed": dismissed,
            "source": source,
        }))
    elif dismissed:
        console.print(f"[green]Dismissed: {session_id}[/green]")
        console.print(f"  Source: {source}")
    else:
        console.print("[red]Failed to dismiss[/red]")
        raise SystemExit(1)
