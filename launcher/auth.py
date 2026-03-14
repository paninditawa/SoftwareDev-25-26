from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import requests


class FirebaseAuthError(Exception):
    pass


@dataclass
class AuthSession:
    email: str
    id_token: str
    refresh_token: str
    local_id: str


def _map_error(message: str) -> str:
    known = {
        "EMAIL_EXISTS": "That email is already registered.",
        "EMAIL_NOT_FOUND": "No account found for that email.",
        "INVALID_PASSWORD": "Incorrect password.",
        "USER_DISABLED": "This account has been disabled.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "CREDENTIAL_TOO_OLD_LOGIN_AGAIN": "Please sign in again before deleting your account.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
        "MISSING_FIREBASE_API_KEY": "Firebase API key is missing.",
    }
    return known.get(message, f"Authentication failed: {message}")


class FirebaseAuthClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "FirebaseAuthClient":
        api_key = os.environ.get("FIREBASE_API_KEY")
        if api_key:
            return cls(api_key)

        executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
        current_dir = Path.cwd()

        candidate_files = [
            workspace_root / ".streamlit" / "secrets.toml",
            workspace_root / "testing" / ".streamlit" / "secrets.toml",
        ]
        if executable_dir is not None:
            candidate_files.extend(
                [
                    executable_dir / ".streamlit" / "secrets.toml",
                    executable_dir / "testing" / ".streamlit" / "secrets.toml",
                ]
            )
        candidate_files.extend(
            [
                current_dir / ".streamlit" / "secrets.toml",
                current_dir / "testing" / ".streamlit" / "secrets.toml",
            ]
        )
        for secret_file in candidate_files:
            try:
                if secret_file.exists():
                    data = tomllib.loads(secret_file.read_text(encoding="utf-8"))
                    api_key = data.get("firebase_api_key")
                    if api_key:
                        return cls(api_key)
            except Exception:
                continue

        return cls(None)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, endpoint: str, payload: dict) -> dict:
        if not self.api_key:
            raise FirebaseAuthError(_map_error("MISSING_FIREBASE_API_KEY"))

        url = f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={self.api_key}"
        try:
            response = requests.post(url, json=payload, timeout=15)
            data = response.json()
        except Exception as exc:
            raise FirebaseAuthError(f"Network error: {exc}") from exc

        if not response.ok:
            message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
            raise FirebaseAuthError(_map_error(message))
        return data

    def sign_in(self, email: str, password: str) -> AuthSession:
        data = self._request(
            "accounts:signInWithPassword",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return AuthSession(
            email=data.get("email", email),
            id_token=data.get("idToken", ""),
            refresh_token=data.get("refreshToken", ""),
            local_id=data.get("localId", ""),
        )

    def sign_up(self, email: str, password: str) -> AuthSession:
        data = self._request(
            "accounts:signUp",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return AuthSession(
            email=data.get("email", email),
            id_token=data.get("idToken", ""),
            refresh_token=data.get("refreshToken", ""),
            local_id=data.get("localId", ""),
        )

    def delete_account(self, session: AuthSession) -> None:
        self._request("accounts:delete", {"idToken": session.id_token})
