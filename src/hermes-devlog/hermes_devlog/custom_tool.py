"""Thin custom-tool adapter delegating to the CLI dispatch."""

from .cli import _dispatch
from .errors import CoordinatorError


def hermes_devlog(operation: str, payload: dict) -> dict:
    """Execute a supported declarative operation without external actions."""
    try:
        return {"ok": True, **_dispatch(operation, payload)}
    except CoordinatorError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except (KeyError, TypeError) as exc:
        return {"ok": False, "error": {"code": "invalid_input", "message": str(exc)}}
