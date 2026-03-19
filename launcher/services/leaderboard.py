"""
launcher/scoreboard.py
----------------------
Community scoreboard backed by Supabase.

Schema (run once in your Supabase SQL editor):

    create table if not exists scores (
        id          bigserial primary key,
        user_id     text        not null,
        username    text        not null,
        game        text        not null,   -- e.g. 'battleship', 'hangman', 'maze'
        wins        integer     not null default 0,
        updated_at  timestamptz not null default now(),
        unique (user_id, game)
    );

    -- Allow any authenticated user to read all rows.
    alter table scores enable row level security;
    create policy "read all" on scores for select using (true);
    -- Allow a user to upsert only their own row.
    create policy "own upsert" on scores for insert with check (auth.uid()::text = user_id);
    create policy "own update" on scores for update using (auth.uid()::text = user_id);

Usage:
    from launcher.services.leaderboard import Scoreboard
    sb = Scoreboard.from_workspace(REPO_ROOT)
    sb.record_win(user_id, username, "battleship")
    rows = sb.top_scores("battleship", limit=10)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_supabase_config(repo_root: Path) -> tuple[str, str]:
    """
    Return (supabase_url, anon_key) from supabase_project.py.
    Raises RuntimeError when required Supabase settings are missing.
    """
    candidates = [
        repo_root / "supabase_project.py",
        repo_root / "launcher" / "supabase_project.py",
    ]
    namespace: dict[str, Any] = {}
    for path in candidates:
        if path.exists():
            exec(compile(path.read_text(), str(path), "exec"), namespace)  # noqa: S102
            break

    url = namespace.get("SUPABASE_URL", "").strip()
    key = namespace.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not key or url.startswith("<"):
        raise RuntimeError("Supabase config is required for scoreboard.")
    return url, key


def _http(method: str, url: str, headers: dict, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Supabase HTTP {exc.code}: {exc.read().decode()}") from exc


# ---------------------------------------------------------------------------
# Scoreboard
# ---------------------------------------------------------------------------

class Scoreboard:
    """Thin Supabase REST client for the scores table."""

    TABLE = "scores"

    def __init__(self, supabase_url: str, anon_key: str, id_token: str = "") -> None:
        self._base = supabase_url.rstrip("/") + f"/rest/v1/{self.TABLE}"
        self._anon_key = anon_key
        self._id_token = id_token  # JWT from auth session — used for write operations

    @classmethod
    def from_workspace(cls, repo_root: Path, id_token: str = "") -> "Scoreboard":
        url, key = _load_supabase_config(repo_root)
        return cls(url, key, id_token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_headers(self) -> dict:
        return {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {self._anon_key}",
            "Content-Type": "application/json",
        }

    def _write_headers(self) -> dict:
        token = self._id_token or self._anon_key
        return {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_win(self, user_id: str, username: str, game: str) -> None:
        """
        Increment the win counter for (user_id, game) by 1.
        Uses an upsert so the row is created on first win.
        The Supabase RPC approach avoids a read-modify-write race condition.
        If the RPC is unavailable, it uses a read-then-upsert compatibility path.
        """
        # Try RPC first (atomic increment)
        rpc_url = self._base.replace(f"/rest/v1/{self.TABLE}", "/rest/v1/rpc/increment_wins")
        try:
            _http(
                "POST",
                rpc_url,
                self._write_headers(),
                {"p_user_id": user_id, "p_username": username, "p_game": game},
            )
            return
        except Exception:
            pass

        # Compatibility path: fetch current wins then upsert with +1
        fetch_url = (
            f"{self._base}?user_id=eq.{user_id}&game=eq.{game}&select=wins"
        )
        try:
            rows = _http("GET", fetch_url, self._read_headers())
            current = rows[0]["wins"] if rows else 0
        except Exception:
            current = 0

        payload = {
            "user_id": user_id,
            "username": username,
            "game": game,
            "wins": current + 1,
            "updated_at": "now()",
        }
        _http("POST", self._base, self._write_headers(), payload)

    def top_scores(self, game: str, limit: int = 10) -> list[dict]:
        """
        Return the top `limit` rows for `game`, ordered by wins descending.
        Each row: {"username": str, "wins": int, "updated_at": str}
        """
        url = (
            f"{self._base}"
            f"?game=eq.{game}"
            f"&select=username,wins,updated_at"
            f"&order=wins.desc"
            f"&limit={limit}"
        )
        rows = _http("GET", url, self._read_headers())
        return rows or []

    def all_games_top(self, limit_per_game: int = 5) -> dict[str, list[dict]]:
        """
        Return top scores for every game that has at least one entry.
        Returns {game_name: [rows]}
        """
        url = f"{self._base}?select=game,username,wins,updated_at&order=wins.desc&limit=200"
        rows = _http("GET", url, self._read_headers()) or []

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            g = row["game"]
            if g not in grouped:
                grouped[g] = []
            if len(grouped[g]) < limit_per_game:
                grouped[g].append(row)
        return grouped