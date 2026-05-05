"""
Chat service for real-time messaging with Supabase.
Handles message persistence and polling for new messages.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from supabase_project import SUPABASE_URL, SUPABASE_ANON_KEY


def _load_supabase_config(repo_root: Path) -> tuple[str, str]:
    """Load Supabase credentials from config."""
    candidates = [
        repo_root / "supabase_project.py",
        repo_root / "launcher" / "supabase_project.py",
    ]
    namespace: dict[str, Any] = {}
    for path in candidates:
        if path.exists():
            exec(compile(path.read_text(), str(path), "exec"), namespace)
            break

    url = SUPABASE_URL
    key = SUPABASE_ANON_KEY
    if not url or not key:
        raise RuntimeError("Supabase config required for chat.")
    return url, key


class ChatService:
    """Thin Supabase REST client for the chat_messages table."""

    TABLE = "chat_messages"

    def __init__(self, supabase_url: str, anon_key: str, id_token: str = "") -> None:
        self._base = supabase_url.rstrip("/") + f"/rest/v1/{self.TABLE}"
        self._anon_key = anon_key
        self._id_token = id_token

    @classmethod
    def from_workspace(cls, repo_root: Path, id_token: str = "") -> ChatService:
        """Create chat service from workspace config."""
        url, key = _load_supabase_config(repo_root)
        return cls(url, key, id_token)

    def _headers(self, with_auth: bool = True) -> dict:
        """Build request headers."""
        headers = {
            "apikey": self._anon_key,
            "Content-Type": "application/json",
        }
        if with_auth and self._id_token:
            headers["Authorization"] = f"Bearer {self._id_token}"
        return headers

    def send_message(
        self, user_id: str, username: str, content: str, game_type: str = "general"
    ) -> dict:
        """Send a chat message."""
        body = {
            "user_id": user_id,
            "username": username,
            "content": content,
            "game_type": game_type,
        }
        req = urllib.request.Request(
            self._base,
            data=json.dumps(body).encode(),
            headers=self._headers(with_auth=True),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                if not data:
                    return {}
                return json.loads(data)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Failed to send message: {exc.read().decode()}") from exc

    def get_messages(
        self, game_type: str = "general", limit: int = 50, since_minutes: int = 60
    ) -> list[dict]:
        """Fetch recent chat messages."""
        since = datetime.utcnow() - timedelta(minutes=since_minutes)
        timestamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = [
            ("select", "*"),
            ("game_type", f"eq.{game_type}"),
            ("created_at", f"gte.{timestamp}"),
            ("order", "created_at.desc"),
            ("limit", str(limit)),
        ]
        query = urllib.parse.urlencode(params, safe=":-TZ")
        url = f"{self._base}?{query}"
        req = urllib.request.Request(url, headers=self._headers(with_auth=False), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                if not data:
                    return []
                messages = json.loads(data)
                return list(reversed(messages))  # Show oldest first
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch messages: {exc.read().decode()}") from exc