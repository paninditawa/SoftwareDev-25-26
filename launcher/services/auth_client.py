"""
Supabase authentication client for the HelloWorld GameSpace launcher.

This module provides three things:
  AuthError   — an exception raised whenever sign-in or sign-up fails.
  AuthSession — a simple data class that stores the tokens and user info
                returned after a successful auth request.
  AuthClient  — makes HTTP requests to the Supabase Auth REST API.
                Call AuthClient.from_workspace() to auto-detect credentials
                from environment variables or from a local supabase_project.py
                config file.
"""
from __future__ import annotations

# importlib.util lets us load a Python config file by its file path at runtime.
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from supabase_project import SUPABASE_URL, SUPABASE_ANON_KEY

# requests is used to call the Supabase REST API endpoints.
import requests


# Raised whenever an auth request fails (wrong password, network error, etc.).
class AuthError(Exception):
    pass


@dataclass
class AuthSession:
    # All the information we need to remember after a successful sign-in.
    email: str
    id_token: str       # short-lived JWT for API requests
    refresh_token: str  # long-lived token to obtain new id_tokens
    local_id: str       # stable UUID assigned by Supabase to this user
    username: str | None = None  # display name set during account creation


def _extract_username(user: dict | None) -> str | None:
    # Pull a display name out of the Supabase user_metadata dict, trying several key names.
    if not isinstance(user, dict):
        return None
    metadata = user.get("user_metadata")
    if isinstance(metadata, dict):
        for key in ("username", "display_name", "name"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _load_value_from_python_config(config_file: Path, keys: tuple[str, ...]) -> str | None:
    # Dynamically load a Python config file and return the first matching variable value.
    if not config_file.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("local_auth_config", str(config_file))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        return None

    for key_name in keys:
        value = getattr(module, key_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_usable_url(value: str | None) -> bool:
    # Return True only if the string looks like a real HTTPS URL (not a placeholder).
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    placeholders = (
        "SUPABASE_URL"
    )
    if normalized in placeholders:
        return False
    return normalized.startswith("http://") or normalized.startswith("https://")


def _is_usable_supabase_key(value: str | None) -> bool:
    # Return True if the string looks like a real Supabase anon key (not a placeholder).
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    placeholders = (
        "SUPABASE_ANON_KEY"
    )
    return normalized not in placeholders


class AuthClient:
    def __init__(self, supabase_url: str | None, supabase_anon_key: str | None, cache_file: Path | None = None) -> None:
        # Strip trailing slashes from the URL so path joins always work correctly.
        self.supabase_url = supabase_url.rstrip("/") if isinstance(supabase_url, str) else None
        self.supabase_anon_key = supabase_anon_key.strip() if isinstance(supabase_anon_key, str) else None
        self.cache_file = cache_file

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "AuthClient":
        cache_file = workspace_root / ".auth_username_cache.json"
        # Try to get credentials from environment variables first (highest priority).
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY")
        if _is_usable_url(supabase_url) and _is_usable_supabase_key(supabase_anon_key):
            return cls(supabase_url.strip(), supabase_anon_key.strip(), cache_file=cache_file)

        current_dir = Path.cwd()

        # Fall back to looking for supabase_project.py in the workspace or current directory.
        candidate_configs = [
            workspace_root / "supabase_project.py",
            workspace_root / "launcher" / "supabase_project.py",
        ]
        candidate_configs.extend(
            [
                current_dir / "supabase_project.py",
                current_dir / "launcher" / "supabase_project.py",
            ]
        )

        for config_file in candidate_configs:
            supabase_url = _load_value_from_python_config(config_file, ("SUPABASE_URL", "supabase_url"))
            supabase_anon_key = _load_value_from_python_config(config_file, ("SUPABASE_ANON_KEY", "supabase_anon_key"))
            if _is_usable_url(supabase_url) and _is_usable_supabase_key(supabase_anon_key):
                return cls(supabase_url, supabase_anon_key, cache_file=cache_file)

        # No valid credentials found; the client will return False for is_configured().
        return cls(None, None, cache_file=cache_file)

    def _load_username_cache(self) -> dict[str, str]:
        if self.cache_file is None or not self.cache_file.exists():
            return {}
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(username).strip().casefold(): str(email).strip()
            for username, email in data.items()
            if isinstance(username, str) and isinstance(email, str) and username.strip() and email.strip()
        }

    def _save_username_cache(self, cache: dict[str, str]) -> None:
        if self.cache_file is None:
            return
        try:
            self.cache_file.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    def remember_username_email(self, username: str, email: str) -> None:
        normalized_username = username.strip().casefold() if isinstance(username, str) else ""
        normalized_email = email.strip() if isinstance(email, str) else ""
        if not normalized_username or not normalized_email:
            return
        cache = self._load_username_cache()
        cache[normalized_username] = normalized_email
        self._save_username_cache(cache)

    def is_configured(self) -> bool:
        # Returns True only if both URL and key look like real values (not placeholders).
        return _is_usable_url(self.supabase_url) and _is_usable_supabase_key(self.supabase_anon_key)

    def _request(self, method: str, path: str, payload: dict | None = None, user_token: str | None = None) -> dict:
        # Make a single authenticated request to the Supabase Auth REST API.
        if not self.is_configured():
            raise AuthError("Supabase auth is not configured.")

        # Use the caller's token if provided; otherwise use the project anon key.
        auth_token = user_token.strip() if isinstance(user_token, str) and user_token.strip() else self.supabase_anon_key
        headers = {
            "apikey": self.supabase_anon_key,
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.supabase_url}{path}"
        try:
            response = requests.request(method, url, json=payload, headers=headers, timeout=15)
        except Exception as exc:
            raise AuthError(f"Supabase network error: {exc}") from exc

        # 204 No Content is a success with no body.
        if response.status_code == 204:
            return {}

        data: dict | str = {}
        if response.text:
            try:
                data = response.json()
            except Exception:
                data = response.text

        if not response.ok:
            # Extract a human-readable error message from whatever shape the response body has.
            detail = "Authentication failed."
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    err = err.get("message") or err.get("error_description")
                detail = data.get("msg") or data.get("message") or data.get("error_description") or err or detail
            elif isinstance(data, str) and data.strip():
                detail = data.strip()

            if method.upper() == "DELETE" and path == "/auth/v1/user" and response.status_code in {401, 403}:
                detail = (
                    f"{detail} (Supabase may require recent sign-in, or user self-delete may be disabled in Auth settings.)"
                )
            raise AuthError(str(detail))
        return data

    def sign_in(self, email: str, password: str) -> AuthSession:
        # Authenticate an existing account and return a session with tokens.
        data = self._request("POST", "/auth/v1/token?grant_type=password", {"email": email, "password": password})
        user = data.get("user") if isinstance(data, dict) else {}
        return AuthSession(
            email=(user or {}).get("email", email),
            id_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            local_id=(user or {}).get("id", ""),
            username=_extract_username(user),
        )

    def lookup_email_by_username(self, username: str) -> str | None:
        # Resolve a username to email from the local cache first, then try Supabase.
        if not self.is_configured() or not username.strip():
            cache = self._load_username_cache()
            return cache.get(username.strip().casefold())
        cache = self._load_username_cache()
        cached_email = cache.get(username.strip().casefold())
        if cached_email:
            return cached_email
        try:
            import urllib.parse
            encoded = urllib.parse.quote(username.strip())
            headers = {
                "apikey": self.supabase_anon_key,
                "Authorization": f"Bearer {self.supabase_anon_key}",
            }
            url = f"{self.supabase_url}/rest/v1/scores?username=eq.{encoded}&select=email&limit=1"
            response = requests.get(url, headers=headers, timeout=10)
            if response.ok:
                rows = response.json()
                if rows and isinstance(rows, list) and rows[0].get("email"):
                    email = rows[0]["email"]
                    self.remember_username_email(username, email)
                    return email
        except Exception:
            pass
        return None

    def _store_email_in_scores(self, user_id: str, username: str, email: str, id_token: str) -> None:
        # Upsert a minimal row in the scores table so username→email lookup works at sign-in.
        self.remember_username_email(username, email)
        if not self.is_configured():
            return
        try:
            headers = {
                "apikey": self.supabase_anon_key,
                "Authorization": f"Bearer {id_token}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            }
            payload = {"user_id": user_id, "username": username, "email": email, "game": "__profile__", "wins": 0}
            url = f"{self.supabase_url}/rest/v1/scores"
            requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception:
            pass

    def sign_up(self, email: str, password: str, username: str | None = None) -> AuthSession:
        # Create a new account, optionally storing a username in user_metadata.
        payload: dict[str, object] = {"email": email, "password": password}
        if isinstance(username, str) and username.strip():
            payload["data"] = {"username": username.strip()}

        data = self._request("POST", "/auth/v1/signup", payload)
        user = data.get("user") if isinstance(data, dict) else {}
        session = AuthSession(
            email=(user or {}).get("email", email),
            id_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            local_id=(user or {}).get("id", ""),
            username=_extract_username(user) or (username.strip() if isinstance(username, str) and username.strip() else None),
        )
        if session.username:
            self.remember_username_email(session.username, session.email)
        # Store email in the scores table so username-based sign-in works later.
        if session.local_id and session.username and session.id_token:
            self._store_email_in_scores(session.local_id, session.username, session.email, session.id_token)
        return session


