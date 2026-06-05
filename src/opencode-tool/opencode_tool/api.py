"""API client for OpenCode server."""

import json
import subprocess
import sys
from typing import Any, Optional

import requests

from .config import get_server_url, get_config_value
from .registry import update_server_last_used, find_server_by_url
class OpenCodeAPI:
    """OpenCode server API client."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or get_server_url()
        self._setup_auth()
        self._server_id = None

    def _find_server_id(self) -> Optional[str]:
        """Find server ID for current base_url."""
        if self._server_id:
            return self._server_id
        server = find_server_by_url(self.base_url)
        if server:
            self._server_id = server.get("id")
            return self._server_id
        return None

    def _refresh_last_used(self):
        """Refresh last_used_at timestamp for the current server."""
        server_id = self._find_server_id()
        if server_id:
            try:
                update_server_last_used(server_id)
            except Exception:
                pass  # Non-critical, don't fail the request
    
    def _setup_auth(self):
        """Setup authentication from config."""
        """Setup authentication from config."""
        self.auth = None
        
        # Check config for password
        password = get_config_value("opencode_server_password")
        if password:
            username = get_config_value("opencode_server_username") or "opencode"
            self.auth = (username, password)
        
        # Environment variable takes precedence
        import os
        env_password = os.environ.get("OPENCODE_SERVER_PASSWORD")
        if env_password:
            username = os.environ.get("OPENCODE_SERVER_USERNAME") or "opencode"
            self.auth = (username, env_password)
    
    def _get(self, path: str) -> Any:
        """Make a GET request."""
        self._refresh_last_used()
        try:
            resp = requests.get(f"{self.base_url}{path}", auth=self.auth, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API error: {e}")
    
    def _post(self, path: str, data: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
        """Make a POST request."""
        self._refresh_last_used()
        try:
            resp = requests.post(f"{self.base_url}{path}", json=data, auth=self.auth, headers=headers or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API error: {e}")
    
    def health(self) -> dict:
        """Check server health."""
        return self._get("/global/health")
    
    def is_healthy(self) -> bool:
        """Check if server is healthy."""
        try:
            health = self.health()
            return health.get("healthy", False)
        except:
            return False
    
    def get_sessions(self) -> list:
        """List all sessions."""
        return self._get("/session")
    
    def get_session_status(self, directory: str = None) -> dict:
        """Get status of all sessions.
        
        Args:
            directory: Optional directory scope. For localhost servers without
                       an explicit directory, defaults to cwd (same as run.py).
                       The endpoint returns {} without directory in 1.15.7+.
        """
        # Default directory for localhost (matches run.py --dir logic)
        if directory is None:
            server_url = self.base_url or ""
            if "localhost" in server_url or "127.0.0.1" in server_url:
                from pathlib import Path
                directory = str(Path.cwd())
        
        path = "/session/status"
        if directory:
            path += f"?directory={directory}"
        return self._get(path)
    
    def get_session(self, session_id: str) -> dict:
        """Get session details."""
        return self._get(f"/session/{session_id}")
    
    def get_session_messages(self, session_id: str) -> list:
        """Get messages for a session."""
        return self._get(f"/session/{session_id}/message")
    
    def abort_session(self, session_id: str) -> bool:
        """Abort a running session."""
        result = self._post(f"/session/{session_id}/abort")
        return result is True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session permanently.

        Tries DELETE /session/{id} first, falls back to abort if not supported.
        Use for truly unrecoverable sessions to clean up dirty state.
        """
        try:
            resp = requests.delete(
                f"{self.base_url}/session/{session_id}",
                auth=self.auth,
                timeout=10,
            )
            if resp.status_code in (200, 204):
                return True
            # DELETE not supported — fall back to abort
            return self.abort_session(session_id)
        except requests.exceptions.RequestException:
            # DELETE endpoint doesn't exist — fall back to abort
            return self.abort_session(session_id)
    
    def get_permissions(self) -> list:
        """Get all pending permissions."""
        return self._get("/permission")
    
    def reply_permission(self, request_id: str, reply: str) -> bool:
        """Reply to a permission request."""
        result = self._post(f"/permission/{request_id}/reply", {"reply": reply})
        return result is True
    
    def get_questions(self) -> list:
        """Get all pending questions."""
        return self._get("/question")
    
    def reply_question(self, request_id: str, answers: list) -> bool:
        """Reply to a question request."""
        result = self._post(f"/question/{request_id}/reply", {"answers": answers})
        return result is True
    
    def reject_question(self, request_id: str) -> bool:
        """Reject a question request."""
        result = self._post(f"/question/{request_id}/reject")
        return result is True

    def _patch(self, path: str, data: dict) -> Any:
        """Make a PATCH request."""
        try:
            resp = requests.patch(f"{self.base_url}{path}", json=data, auth=self.auth, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API error: {e}")

    def patch_part(self, session_id: str, message_id: str, part_id: str, state: dict) -> dict:
        """Patch a message part's state (e.g., dismiss a question tool call)."""
        return self._patch(
            f"/session/{session_id}/message/{message_id}/part/{part_id}",
            {"state": state}
        )

    def create_session(self, model: Optional[str] = None, variant: Optional[str] = None,
                       directory: Optional[str] = None, provider: Optional[str] = None) -> dict:
        """Create a new session.
        
        Args:
            model: Model ID (e.g., "mimo-v2.5")
            variant: Variant (e.g., "high", "max")
            directory: Working directory (sent via x-opencode-directory header)
            provider: Provider ID (e.g., "opencode-go"). If None, server uses default.
        
        Returns:
            Session info dict with 'id' field
        """
        data = {}
        
        if model or variant:
            model_data = {}
            if model:
                model_data["id"] = model
                if provider:
                    model_data["providerID"] = provider
            if variant:
                model_data["variant"] = variant
            if model_data:
                data["model"] = model_data
        
        # Pass directory via header (server middleware reads x-opencode-directory)
        headers = {}
        if directory:
            headers["x-opencode-directory"] = directory
        
        return self._post("/session", data, headers=headers)
    
    def send_message_async(self, session_id: str, prompt: str,
                           model: Optional[str] = None, variant: Optional[str] = None,
                           provider: Optional[str] = None, directory: Optional[str] = None) -> bool:
        """Send a message to a session asynchronously (fire and forget).
        
        Args:
            session_id: Session ID
            prompt: Message text
            model: Model ID to use (optional, overrides session default)
            variant: Variant to use (optional)
            provider: Provider ID (optional). If None, server uses session default.
            directory: Working directory (sent via x-opencode-directory header).
        
        Returns:
            True if accepted (204), raises on error
        """
        data = {
            "parts": [{"type": "text", "text": prompt}]
        }
        
        if model:
            data["model"] = {
                "modelID": model
            }
            if provider:
                data["model"]["providerID"] = provider
        
        if variant:
            data["variant"] = variant
        
        # Build headers with directory context
        headers = {}
        if directory:
            headers["x-opencode-directory"] = directory

        # prompt_async returns 204 (no content) on success
        try:
            resp = requests.post(
                f"{self.base_url}/session/{session_id}/prompt_async",
                json=data,
                auth=self.auth,
                headers=headers,
                timeout=10
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            raise Exception(f"API error: {e}")
    
    def send_message(self, session_id: str, prompt: str,
                     model: Optional[str] = None, variant: Optional[str] = None,
                     provider: Optional[str] = None) -> dict:
        """Send a message to a session and wait for response.
        
        Args:
            session_id: Session ID
            prompt: Message text
            model: Model ID to use (optional)
            variant: Variant to use (optional)
            provider: Provider ID (optional)
        
        Returns:
            Response message dict
        """
        data = {
            "parts": [{"type": "text", "text": prompt}]
        }
        
        if model:
            data["model"] = {
                "modelID": model
            }
            if provider:
                data["model"]["providerID"] = provider
        
        if variant:
            data["variant"] = variant
        
        return self._post(f"/session/{session_id}/message", data)
    
    def list_models(self) -> list:
        """List all available models from all providers.

        Returns:
            List of model dicts with provider, model_id, name fields
        """
        try:
            data = self._get("/provider")
            providers = data.get("all", [])
        except Exception:
            return []

        models = []
        for provider in providers:
            provider_id = provider.get("id", "")
            provider_models = provider.get("models", {})
            # models is a dict keyed by model ID
            if isinstance(provider_models, dict):
                for model_id, m in provider_models.items():
                    models.append({
                        "provider": provider_id,
                        "model_id": model_id,
                        "name": m.get("name", model_id),
                    })
            elif isinstance(provider_models, list):
                for m in provider_models:
                    models.append({
                        "provider": provider_id,
                        "model_id": m.get("id", ""),
                        "name": m.get("name", m.get("id", "")),
                    })
        return models

    # ── TUI methods (safe — publish events, no consumption) ──

    def tui_execute_command(self, command: str) -> bool:
        """Execute a TUI command (publishes event, no race condition)."""
        result = self._post("/tui/execute-command", {"command": command})
        return result is True

    def tui_publish(self, event_type: str, properties: dict) -> bool:
        """Publish a TUI event."""
        result = self._post("/tui/publish", {"type": event_type, "properties": properties})
        return result is True

    def tui_show_toast(self, message: str, title: Optional[str] = None,
                       variant: str = "info") -> bool:
        """Show a toast notification in the TUI."""
        data: dict[str, Any] = {"message": message, "variant": variant}
        if title:
            data["title"] = title
        result = self._post("/tui/show-toast", data)
        return result is True

    def tui_select_session(self, session_id: str) -> bool:
        """Navigate TUI to a specific session."""
        result = self._post("/tui/select-session", {"sessionID": session_id})
        return result is True

    def tui_control_next(self, timeout: int = 5) -> Optional[dict]:
        """Long-poll for the next TUI control request.

        Returns the request dict or None on timeout.
        Only useful in isolated mode (no competition).
        """
        try:
            resp = requests.get(
                f"{self.base_url}/tui/control/next",
                auth=self.auth,
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if data else None
            return None
        except Exception:
            return None

    def tui_control_response(self, body: Any) -> bool:
        """Respond to a TUI control request."""
        result = self._post("/tui/control/response", {"body": body})
        return result is True
