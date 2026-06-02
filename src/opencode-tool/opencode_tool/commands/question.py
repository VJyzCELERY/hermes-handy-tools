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
    """Scan session messages for pending question tool calls.
    
    Fallback when GET /question API misses questions (known issue in v1.15.7+).
    Returns a list of question-like dicts compatible with the display format.
    """
    try:
        messages = api.get_session_messages(session_id)
    except:
        return []

    if not messages:
        return []

    results = []
    for msg in messages:
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
                        results.append({
                            "id": state.get("requestID") or part.get("callID", "?"),
                            "sessionID": session_id,
                            "questions": questions_list,
                        })

    return results


@question.command("get")
@click.argument("session_id")
def get_questions(session_id: str):
    """List pending question requests for a session."""
    api = OpenCodeAPI()

    # Try the REST API first
    questions = [q for q in api.get_questions() if q.get("sessionID") == session_id]

    # Fallback: scan session messages (GET /question can miss questions in v1.15.7+)
    if not questions:
        questions = _scan_session_questions(api, session_id)

    if not questions:
        console.print("[yellow]no pending questions[/yellow]")
        return

    for q in questions:
        qid = q.get("id", "?")
        console.print(f"[green][{qid}[/green]]")
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
    
    # Get the question to understand structure
    questions = api.get_questions()
    req = next((q for q in questions if q.get("id") == request_id), None)
    
    if not req:
        console.print(f"[red]question not found: {request_id}[/red]")
        raise SystemExit(1)
    
    # Build answers array - one per question
    question_list = req.get("questions", [])
    answers_array = []
    
    for i, qi in enumerate(question_list):
        if i < len(answers):
            # Answer provided
            answers_array.append([answers[i]])
        else:
            # No answer provided - use first option as default
            options = qi.get("options", [])
            if options:
                answers_array.append([options[0].get("label", "")])
            else:
                answers_array.append([])
    
    # Send reply
    if api.reply_question(request_id, answers_array):
        console.print(f"[green]replied: {request_id}[/green]")
        for i, ans in enumerate(answers_array):
            console.print(f"  Q{i+1}: {', '.join(ans)}")
    else:
        console.print(f"[red]failed to reply: {request_id}[/red]")
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
