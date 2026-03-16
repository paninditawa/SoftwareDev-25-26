from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import requests


class AuthError(Exception):
    pass


@dataclass
class AuthSession:
    email: str
    id_token: str
    refresh_token: str
    local_id: str
    username: str | None = None


def _extract_username(user: dict | None) -> str | None:
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
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    placeholders = (
        "REPLACE_WITH_SUPABASE_URL",
        "YOUR_SUPABASE_URL",
        "https://YOUR-PROJECT-REF.supabase.co",
    )
    if normalized in placeholders:
        return False
    return normalized.startswith("http://") or normalized.startswith("https://")


def _is_usable_supabase_key(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    placeholders = (
        "REPLACE_WITH_SUPABASE_ANON_KEY",
        "YOUR_SUPABASE_ANON_KEY",
    )
    return normalized not in placeholders


class AuthClient:
    def __init__(self, supabase_url: str | None, supabase_anon_key: str | None) -> None:
        self.supabase_url = supabase_url.rstrip("/") if isinstance(supabase_url, str) else None
        self.supabase_anon_key = supabase_anon_key.strip() if isinstance(supabase_anon_key, str) else None

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "AuthClient":
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY")
        if _is_usable_url(supabase_url) and _is_usable_supabase_key(supabase_anon_key):
            return cls(supabase_url.strip(), supabase_anon_key.strip())

        executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
        current_dir = Path.cwd()

        candidate_configs = [
            workspace_root / "supabase_project.py",
            workspace_root / "launcher" / "supabase_project.py",
        ]
        if executable_dir is not None:
            candidate_configs.extend(
                [
                    executable_dir / "supabase_project.py",
                    executable_dir / "launcher" / "supabase_project.py",
                ]
            )
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
                return cls(supabase_url, supabase_anon_key)

        return cls(None, None)

    def is_configured(self) -> bool:
        return _is_usable_url(self.supabase_url) and _is_usable_supabase_key(self.supabase_anon_key)

    def _request(self, method: str, path: str, payload: dict | None = None, user_token: str | None = None) -> dict:
        if not self.is_configured():
            raise AuthError("Supabase auth is not configured.")

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

        if response.status_code == 204:
            return {}

        data: dict | str = {}
        if response.text:
            try:
                data = response.json()
            except Exception:
                data = response.text

        if not response.ok:
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
        data = self._request("POST", "/auth/v1/token?grant_type=password", {"email": email, "password": password})
        user = data.get("user") if isinstance(data, dict) else {}
        return AuthSession(
            email=(user or {}).get("email", email),
            id_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            local_id=(user or {}).get("id", ""),
            username=_extract_username(user),
        )

    def sign_up(self, email: str, password: str, username: str | None = None) -> AuthSession:
        payload: dict[str, object] = {"email": email, "password": password}
        if isinstance(username, str) and username.strip():
            payload["data"] = {"username": username.strip()}

        data = self._request("POST", "/auth/v1/signup", payload)
        user = data.get("user") if isinstance(data, dict) else {}
        return AuthSession(
            email=(user or {}).get("email", email),
            id_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            local_id=(user or {}).get("id", ""),
            username=_extract_username(user) or (username.strip() if isinstance(username, str) and username.strip() else None),
        )


