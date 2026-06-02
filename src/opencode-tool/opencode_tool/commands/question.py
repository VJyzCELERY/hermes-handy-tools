"""Question management commands."""

import click
from rich.console import Console

from ..api import OpenCodeAPI

console = Console()


@click.group()
def question():
    """Manage OpenCode questions."""
    pass


def _scan_session_questions(api: OpenCodeAPI, session_id: str):
    """Scan session messages for the LATEST pending question tool call.

    GET /question API can return stale questions or miss new ones (v1.15.7+).
    This scans the last assistant message only — same approach used by
    _check_question_blocked in session.py for status detection.

    Returns a list with at most one question dict compatible with the
    display format.
    """
    try:
        messages = api.get_session_messages(session_id)
    except:
        return []

    if not messages:
        return []

    # Scan backwards from the last message, stop after last assistant msg
    for msg in reversed(messages):
        info = msg.get("info", {})
        if info.get("role") != "assistant":
            continue

        parts = msg.get("parts", [])
        for part in parts:
            if part.get("type") == "tool" and part.get("tool") == "question":
                state = part.get("state", {})
                if state.get("status") in ("pending", "running", None):
                    input_data = state.get("input", {})
                    questions_list = input_data.get("questions", [])
                    if questions_list:
                        call_id = part.get("callID", "?")
                        return [{
                            "id": call_id,
                            "sessionID": session_id,
                            "questions": questions_list,
                            "_replyable": False,  # callID alone can't be used for reply
                        }]
        break  # only check the last assistant message

    return []


def _find_question_by_id(api: OpenCodeAPI, request_id: str):
    """Find a question by its request_id or callID.

    1. Try GET /question by id (fast, works when available)
    2. Try GET /question by tool.callID mapping
    3. Fall back to scanning active sessions' messages

    Returns the question dict or None.
    """
    # Fast path: REST API by id
    try:
        questions = api.get_questions()
        req = next((q for q in questions if q.get("id") == request_id), None)
        if req:
            return req

        # Try matching by tool.callID
        req = next((q for q in questions if q.get("tool", {}).get("callID") == request_id), None)
        if req:
            return req
    except:
        pass

    # Fallback: scan active sessions for the question by callID
    try:
        sessions = api.get_sessions()
    except:
        return None

    for s in sessions:
        sid = s.get("id")
        if not sid:
            continue
        try:
            messages = api.get_session_messages(sid)
        except:
            continue

        for msg in messages:
            info = msg.get("info", {})
            if info.get("role") != "assistant":
                continue
            for part in msg.get("parts", []):
                if part.get("type") == "tool" and part.get("tool") == "question":
                    state = part.get("state", {})
                    qid = state.get("requestID") or part.get("callID")
                    if qid == request_id:
                        input_data = state.get("input", {})
                        return {
                            "id": qid,
                            "sessionID": sid,
                            "questions": input_data.get("questions", []),
                        }

    return None


@question.command("get")
@click.argument("session_id")
def get_questions(session_id: str):
    """List pending question requests for a session."""
    api = OpenCodeAPI()

    # Scan session messages for the latest question tool call
    # (GET /question API returns stale data or misses questions in v1.15.7+)
    questions = _scan_session_questions(api, session_id)

    if not questions:
        console.print("[yellow]no pending questions[/yellow]")
        return

    for q in questions:
        qid = q.get("id", "?")
        replyable = q.get("_replyable", True)

        # Try to find the actual request_id for this question
        request_id = None
        try:
            all_questions = api.get_questions()
            match = next((aq for aq in all_questions
                         if aq.get("tool", {}).get("callID") == qid), None)
            if match:
                request_id = match.get("id")
        except:
            pass

        display_id = request_id or qid
        console.print(f"[green][{display_id}[/green]]")
        if not request_id:
            console.print(f"  [dim](question not registered in API — may need TUI to reply)[/dim]")
        for i, qi in enumerate(q.get("questions", [])):
            header = qi.get("header", "?")
            q_text = qi.get("question", "?")
            options = qi.get("options", [])
            multiple = qi.get("multiple", False)
            custom = qi.get("custom", False)

            console.print(f"  Q{i+1}: [cyan]{header}[/cyan]")
            console.print(f"      {q_text}")
            if multiple:
                console.print(f"      (select multiple)")
            console.print(f"      Options:")
            for j, opt in enumerate(options, 1):
                console.print(f"        {j}. {opt.get('label', '?')}: {opt.get('description', '')}")
            if custom:
                console.print(f"        0. (type your own answer)")
            console.print()


@question.command()
@click.argument("request_id")
@click.argument("answers", nargs=-1)
def reply(request_id: str, answers: tuple):
    """Reply to a pending question request."""
    api = OpenCodeAPI()

    # Find the question to understand structure (how many sub-questions, defaults)
    req = _find_question_by_id(api, request_id)

    if req:
        # Build answers array from question structure
        question_list = req.get("questions", [])
        answers_array = []

        for i, qi in enumerate(question_list):
            if i < len(answers):
                answers_array.append([answers[i]])
            else:
                # No answer provided - use first option as default
                options = qi.get("options", [])
                if options:
                    answers_array.append([options[0].get("label", "")])
                else:
                    answers_array.append([])
    else:
        # Question structure not found — send raw answers (one per answer)
        # The POST /question/{id}/reply endpoint works regardless
        if not answers:
            console.print(f"[red]question not found and no answers provided: {request_id}[/red]")
            raise SystemExit(1)
        answers_array = [[a] for a in answers]

    # Send reply
    try:
        if api.reply_question(request_id, answers_array):
            console.print(f"[green]replied: {request_id}[/green]")
            for i, ans in enumerate(answers_array):
                console.print(f"  Q{i+1}: {', '.join(ans)}")
        else:
            console.print(f"[red]failed to reply: {request_id}[/red]")
            raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]failed to reply: {request_id}[/red]")
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Hint: if question not registered in API, use TUI to reply[/dim]")
        raise SystemExit(1)


@question.command()
@click.argument("session_id")
def dismiss(session_id: str):
    """Dismiss a pending question by interrupting the session.

    This stops the agent and clears the question block.
    Use when question is not registered in API (shows 'may need TUI to reply').
    """
    import requests as req
    api = OpenCodeAPI()

    # Abort the session to clear the question block
    try:
        api.abort_session(session_id)
        console.print(f"[green]dismissed: {session_id}[/green]")
        console.print(f"[dim]Session interrupted — agent stopped, question cleared[/dim]")
    except Exception as e:
        console.print(f"[red]failed to dismiss: {e}[/red]")
        raise SystemExit(1)


@question.command()
@click.argument("request_id")
def reject(request_id: str):
    """Reject a pending question request."""
    api = OpenCodeAPI()

    if api.reject_question(request_id):
        console.print(f"[green]rejected: {request_id}[/green]")
    else:
        console.print(f"[red]failed to reject: {request_id}[/red]")
        raise SystemExit(1)
