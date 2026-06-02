"""API client for OpenCode server."""

import json
import subprocess
import sys
from typing import Any, Optional

import requests

from .config import get_server_url, get_config_value


class OpenCodeAPI:
    """OpenCode server API client."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or get_server_url()
        self._setup_auth()
    
    def _setup_auth(self):
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
        try:
            resp = requests.get(f"{self.base_url}{path}", auth=self.auth, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API error: {e}")
    
    def _post(self, path: str, data: Optional[dict] = None) -> Any:
        """Make a POST request."""
        try:
            resp = requests.post(f"{self.base_url}{path}", json=data, auth=self.auth, timeout=10)
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
    
    def get_session_status(self) -> dict:
        """Get status of all sessions."""
        return self._get("/session/status")
    
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
